"""The KDS relay feed must only ever offer TODAY's tickets.

A kitchen ticket is useful while the food is being cooked and worthless
afterwards. The feed had no date boundary: any order ever fired whose lines
were never acked still qualified. kot_printed_at only began to be set once
the firing till learned to ack its own print, so everything older carried
NULLs forever — a 2,769-line, 986-order backlog going back to June.

When a till with a working relay came up it started draining that at one
ticket per 8-second poll: 156 tickets printed in a single hour against a
normal 10-40 per DAY, and the kitchen printer ran away with months of stale
orders.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalog.models import Product, UnitOfMeasure
from apps.restaurant import services
from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal

pytestmark = pytest.mark.django_db


@pytest.fixture
def scene(db):
    tenant = Tenant.objects.create(
        business_name="Resort", ntn=f"N{uuid.uuid4().hex[:8]}",
        business_type="sole_proprietor", province="PUNJAB",
        fbr_connection_type="none",
    )
    branch = Branch.objects.create(tenant=tenant, name="Main", code="KK", address="x")
    terminal = Terminal.objects.create(
        tenant=tenant, branch=branch, name="T2",
        device_fingerprint=uuid.uuid4().hex,
    )
    user = get_user_model().objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test", password="x", full_name="C",
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role="cashier")
    product = Product.objects.create(
        tenant=tenant, name="Biryani", sku=uuid.uuid4().hex[:8],
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("500"), cost_price=Decimal("200"),
    )
    return tenant, branch, terminal, user, product


def _fired_order(scene, *, number, days_ago=0):
    """A held order fired to the kitchen, with one UNPRINTED line."""
    tenant, branch, terminal, user, product = scene
    when = timezone.localdate() - dt.timedelta(days=days_ago)
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=user,
        client_uuid=uuid.uuid4(), local_invoice_number=number,
        invoice_date=when, status="pending_sync",
        is_held=True, order_type="dine_in", order_status="sent_to_kitchen",
        kitchen_sent_at=timezone.now(),
        subtotal=Decimal("500"), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal("500"),
        paid_total=Decimal("0"), change_given=Decimal("0"),
    )
    SaleItem.objects.create(
        invoice=inv, line_number=1, product=product,
        product_name=product.name, product_sku=product.sku,
        uom_code=product.uom_id, quantity=Decimal("1"),
        unit_price=Decimal("500"), cost_price=Decimal("200"),
        discount_pct=Decimal("0"), discount_amount=Decimal("0"),
        tax_rate=Decimal("0"), tax_amount=Decimal("0"),
        line_total=Decimal("500"),
        sent_to_kitchen=True, kot_printed_at=None,
    )
    return inv


def _feed(tenant, branch):
    """Exactly the queryset KdsUnprintedView serves to the relay."""
    return list(
        services.open_orders_qs(tenant.id, branch_id=str(branch.id))
        .filter(order_status__in=["sent_to_kitchen", "ready"])
        .filter(invoice_date__gte=timezone.localdate())
        .filter(
            items__sent_to_kitchen=True,
            items__kot_printed_at__isnull=True,
            items__is_cancelled=False,
        )
        .distinct(),
    )


def test_todays_unprinted_ticket_is_offered(scene):
    tenant, branch, *_ = scene
    inv = _fired_order(scene, number="KK-T2-2026-0000900", days_ago=0)

    assert [o.id for o in _feed(tenant, branch)] == [inv.id]


def test_yesterdays_ticket_is_never_reprinted(scene):
    """THE bug: a stale ticket must not come back to the kitchen."""
    tenant, branch, *_ = scene
    _fired_order(scene, number="KK-T2-2026-0000901", days_ago=1)

    assert _feed(tenant, branch) == []


def test_a_months_old_backlog_is_ignored_entirely(scene):
    """986 orders going back to June drained one per poll. Never again."""
    tenant, branch, *_ = scene
    for i in range(10):
        _fired_order(scene, number=f"KK-T2-2026-00009{i:02d}", days_ago=30 + i)

    assert _feed(tenant, branch) == []


def test_old_and_new_together_offers_only_the_new(scene):
    tenant, branch, *_ = scene
    _fired_order(scene, number="KK-T2-2026-0000910", days_ago=7)
    today = _fired_order(scene, number="KK-T2-2026-0000911", days_ago=0)

    assert [o.id for o in _feed(tenant, branch)] == [today.id]


def test_an_acked_ticket_today_is_not_reoffered(scene):
    """The exactly-once guard still holds within the day."""
    tenant, branch, *_ = scene
    inv = _fired_order(scene, number="KK-T2-2026-0000912", days_ago=0)
    SaleItem.objects.filter(invoice=inv).update(kot_printed_at=timezone.now())

    assert _feed(tenant, branch) == []
