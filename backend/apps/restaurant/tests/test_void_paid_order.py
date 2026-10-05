"""A charged order must never be voided by the terminal's cleanup call.

Regression (TDCP Kallar Kahar, Oct 2026): at Charge the terminal fired
sync.kick() (async, finalizes is_held=False) and voidOpenOrder() (immediate
soft-delete) against the SAME client_uuid. The void won the race -- the row
was still is_held=True because the sync had not landed -- so it soft-deleted
the sale the guest had just paid for. The invoice list filters
(is_held=False, deleted_at IS NULL), so 54 paid invoices vanished from the
client admin in a single day.

is_held alone is therefore NOT proof an order is unpaid. A completed payment
is the authority: if money was taken, the order is a sale and is untouchable.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.restaurant.services import void_open_order
from apps.sales.models import Invoice, Payment
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
    return tenant, branch, terminal, user


def _order(tenant, branch, terminal, user, *, number):
    """A held restaurant order, exactly as fire-to-kitchen leaves it."""
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=user,
        client_uuid=uuid.uuid4(), local_invoice_number=number,
        invoice_date="2026-10-03", status="pending_sync",
        is_held=True, order_type="dine_in", order_status="sent_to_kitchen",
        subtotal=Decimal("1000"), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal("1000"),
        paid_total=Decimal("0"), change_given=Decimal("0"),
    )


def test_void_refuses_order_with_completed_payment(scene):
    """The exact production race: row still held, but money already taken."""
    tenant, branch, terminal, user = scene
    inv = _order(tenant, branch, terminal, user, number="KK-T2-2026-0000544")
    Payment.objects.create(
        tenant=tenant, invoice=inv, payment_method="cash",
        amount=Decimal("1000"), status="completed",
    )

    result = void_open_order(tenant_id=tenant.id, client_uuid=inv.client_uuid)

    assert result is None, "a paid order must not be voided"
    inv.refresh_from_db()
    assert inv.deleted_at is None, "paid sale was soft-deleted -- it would vanish from admin"


def test_void_still_removes_a_genuinely_unpaid_order(scene):
    """The legitimate case must keep working: no payment -> void proceeds."""
    tenant, branch, terminal, user = scene
    inv = _order(tenant, branch, terminal, user, number="KK-T2-2026-0000545")

    result = void_open_order(tenant_id=tenant.id, client_uuid=inv.client_uuid)

    assert result is not None
    inv.refresh_from_db()
    assert inv.deleted_at is not None


def test_void_ignores_a_failed_payment(scene):
    """A failed/declined tender is not money taken -- the order stays voidable."""
    tenant, branch, terminal, user = scene
    inv = _order(tenant, branch, terminal, user, number="KK-T2-2026-0000546")
    Payment.objects.create(
        tenant=tenant, invoice=inv, payment_method="card",
        amount=Decimal("1000"), status="failed",
    )

    result = void_open_order(tenant_id=tenant.id, client_uuid=inv.client_uuid)

    assert result is not None, "a declined card must not protect the order"
    inv.refresh_from_db()
    assert inv.deleted_at is not None


def test_charging_a_voided_order_restores_it(scene):
    """End-to-end of the production failure, in order.

    Real sequence from KK-T2-2026-0000534 (fired 09:19:37, voided 09:19:47):
      1. order fired to kitchen        -> held row on the server
      2. cashier charges; voidOpenOrder lands FIRST -> row soft-deleted
      3. the paid invoice sync lands LATER

    Step 3 must resurrect the sale. Before the fix it finalized the row but
    left deleted_at set, so the paid invoice stayed hidden from the admin
    invoice list (which filters deleted_at IS NULL) permanently.
    """
    from apps.sales.services import checkout

    tenant, branch, terminal, user = scene
    held = _order(tenant, branch, terminal, user, number="KK-T2-2026-0000534")
    client_uuid = held.client_uuid

    # 2. the racing void wins (no payment yet, so the new guard allows it)
    voided = void_open_order(tenant_id=tenant.id, client_uuid=client_uuid)
    assert voided is not None
    held.refresh_from_db()
    assert held.deleted_at is not None

    # 3. the paid invoice finally syncs
    from apps.catalog.models import Product, UnitOfMeasure

    product = Product.objects.create(
        tenant=tenant, name="Biryani", sku=uuid.uuid4().hex[:8],
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("1000"), cost_price=Decimal("400"),
    )
    invoice = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=user,
        cash_session=None, customer=None,
        cart_lines=[{
            "product": str(product.id), "quantity": "1",
            "unit_price": "1000", "tax_rate": "0", "is_taxable": False,
        }],
        payments=[{"payment_method": "cash", "amount": "1000"}],
        client_uuid=client_uuid,
        order_type="dine_in",
    )

    assert invoice.id == held.id, "must finalize the same row, not create a duplicate"
    assert invoice.deleted_at is None, "paid sale is still soft-deleted -- hidden from admin"
    assert invoice.is_held is False
    assert invoice.local_invoice_number == "KK-T2-2026-0000534", "number must be preserved"
