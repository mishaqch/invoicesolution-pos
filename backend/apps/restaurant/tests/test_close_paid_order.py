"""Closing a paid open order from the server, without the till.

Normally Charge closes an open order: the terminal syncs the paid invoice and
create_invoice() flips is_held=False on the same row. That makes closing an
order depend ENTIRELY on the till reaching the server — and when it cannot
(old build, lost token, reinstalled machine) the guest pays, leaves, and the
order sits on the Open orders screen forever. 170 orders / PKR 424k at TDCP.

The subtle part: un-holding ALONE would be worse than doing nothing. A later
sync would see is_held=False, treat the row as an already-finalized duplicate
and return early — skipping payments, stock and FBR. So the payment must be
recorded AS the order is closed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.restaurant.services import close_paid_order, open_orders_qs
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


def _order(scene, *, number, status="sent_to_kitchen", total="1000"):
    tenant, branch, terminal, user = scene
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=user,
        client_uuid=uuid.uuid4(), local_invoice_number=number,
        invoice_date="2026-10-17", status="pending_sync",
        is_held=True, order_type="dine_in", order_status=status,
        subtotal=Decimal(total), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal(total),
        paid_total=Decimal("0"), change_given=Decimal("0"),
    )


def test_closes_the_order_and_records_the_payment(scene):
    tenant, _, _, user = scene
    inv = _order(scene, number="KK-T2-2026-0000700")
    assert open_orders_qs(tenant.id).filter(pk=inv.pk).exists()

    close_paid_order(tenant_id=tenant.id, invoice=inv, user=user)

    inv.refresh_from_db()
    assert inv.is_held is False
    assert inv.order_status == "served"
    assert inv.paid_total == Decimal("1000")
    assert inv.status == "finalized"
    # THE critical assertion: the money is recorded, not just the hold cleared.
    assert inv.payments.filter(status="completed").count() == 1
    assert not open_orders_qs(tenant.id).filter(pk=inv.pk).exists()


def test_is_idempotent(scene):
    """Safe to re-run, and safe if the till's own sync lands afterwards."""
    tenant, _, _, user = scene
    inv = _order(scene, number="KK-T2-2026-0000701")

    close_paid_order(tenant_id=tenant.id, invoice=inv, user=user)
    close_paid_order(tenant_id=tenant.id, invoice=inv, user=user)

    inv.refresh_from_db()
    assert inv.payments.count() == 1, "must never double-pay an order"


def test_leaves_an_already_paid_order_untouched(scene):
    tenant, _, _, user = scene
    inv = _order(scene, number="KK-T2-2026-0000702")
    Payment.objects.create(
        tenant=tenant, invoice=inv, payment_method="card",
        amount=Decimal("1000"), status="completed",
    )

    close_paid_order(tenant_id=tenant.id, invoice=inv, user=user)

    inv.refresh_from_db()
    assert inv.payments.count() == 1
    assert inv.payments.first().payment_method == "card", "must not overwrite the tender"


def test_records_a_partial_amount_when_given(scene):
    tenant, _, _, user = scene
    inv = _order(scene, number="KK-T2-2026-0000703", total="1000")

    close_paid_order(tenant_id=tenant.id, invoice=inv,
                     amount=Decimal("800"), payment_method="card", user=user)

    inv.refresh_from_db()
    assert inv.paid_total == Decimal("800")
    assert inv.payments.first().payment_method == "card"


def test_already_closed_order_is_a_noop(scene):
    tenant, _, _, user = scene
    inv = _order(scene, number="KK-T2-2026-0000704")
    inv.is_held = False
    inv.save(update_fields=["is_held"])

    close_paid_order(tenant_id=tenant.id, invoice=inv, user=user)

    inv.refresh_from_db()
    assert inv.payments.count() == 0, "a normally-closed sale must not be re-paid"
