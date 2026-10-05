"""repair_paid_held_invoices must recover PAID sales and nothing else.

This command writes to production data, so the boundary it draws matters:
a completed payment means the sale was charged and belongs in the invoice
list; no payment means a live open table that must stay held.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

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


def _inv(scene, *, number, held=True, deleted=False, paid=False, status="completed"):
    tenant, branch, terminal, user = scene
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=user,
        client_uuid=uuid.uuid4(), local_invoice_number=number,
        invoice_date="2026-10-03", status="pending_sync",
        is_held=held, order_type="dine_in", order_status="sent_to_kitchen",
        deleted_at=timezone.now() if deleted else None,
        subtotal=Decimal("1000"), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal("1000"),
        paid_total=Decimal("0"), change_given=Decimal("0"),
    )
    if paid:
        Payment.objects.create(
            tenant=tenant, invoice=inv, payment_method="cash",
            amount=Decimal("1000"), status=status,
        )
    return inv


def test_dry_run_writes_nothing(scene):
    inv = _inv(scene, number="KK-T2-2026-0000544", paid=True)
    call_command("repair_paid_held_invoices", stdout=StringIO())
    inv.refresh_from_db()
    assert inv.is_held is True, "dry run must not modify data"


def test_apply_recovers_paid_invoice(scene):
    inv = _inv(scene, number="KK-T2-2026-0000544", paid=True, deleted=True)
    call_command("repair_paid_held_invoices", "--apply", stdout=StringIO())
    inv.refresh_from_db()
    assert inv.is_held is False
    assert inv.deleted_at is None
    assert inv.order_status == "served"


def test_apply_leaves_open_table_untouched(scene):
    """The whole point: an unpaid open table stays exactly as it is."""
    inv = _inv(scene, number="KK-T2-2026-0000545", paid=False)
    call_command("repair_paid_held_invoices", "--apply", stdout=StringIO())
    inv.refresh_from_db()
    assert inv.is_held is True, "an open table must not be booked as a sale"
    assert inv.deleted_at is None


def test_failed_payment_does_not_count_as_paid(scene):
    inv = _inv(scene, number="KK-T2-2026-0000546", paid=True, status="failed")
    call_command("repair_paid_held_invoices", "--apply", stdout=StringIO())
    inv.refresh_from_db()
    assert inv.is_held is True, "a declined tender is not money taken"


def test_already_visible_invoice_is_not_touched(scene):
    inv = _inv(scene, number="KK-T2-2026-0000547", held=False, paid=True)
    before = inv.updated_at
    call_command("repair_paid_held_invoices", "--apply", stdout=StringIO())
    inv.refresh_from_db()
    assert inv.updated_at == before, "healthy rows must not be rewritten"


# --- --served-no-payment mode -------------------------------------------
# For orders the void race deleted BEFORE their payment could sync: the
# server has no payment row, so the default mode skips them. The kitchen
# docket is the evidence that the food was cooked and served.

def _fired(scene, *, number, order_status="sent_to_kitchen", deleted=True):
    tenant, branch, terminal, user = scene
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=user,
        client_uuid=uuid.uuid4(), local_invoice_number=number,
        invoice_date="2026-10-03", status="pending_sync",
        is_held=True, order_type="dine_in", order_status=order_status,
        deleted_at=timezone.now() if deleted else None,
        subtotal=Decimal("1000"), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal("1000"),
        paid_total=Decimal("0"), change_given=Decimal("0"),
    )


def test_served_mode_recovers_a_fired_order_with_no_payment(scene):
    """KK-T2-2026-0000544: cooked, served, then deleted by the race."""
    inv = _fired(scene, number="KK-T2-2026-0000544")
    call_command("repair_paid_held_invoices", "--served-no-payment", "--apply",
                 stdout=StringIO())
    inv.refresh_from_db()
    assert inv.deleted_at is None
    assert inv.is_held is False
    assert inv.order_status == "served"


def test_served_mode_leaves_an_unfired_draft_alone(scene):
    """KK-T2-2026-0000533: never sent to the kitchen => abandoned draft."""
    inv = _fired(scene, number="KK-T2-2026-0000533", order_status="open")
    call_command("repair_paid_held_invoices", "--served-no-payment", "--apply",
                 stdout=StringIO())
    inv.refresh_from_db()
    assert inv.deleted_at is not None, "an unfired draft is not a sale"
    assert inv.is_held is True


def test_served_mode_leaves_live_open_tables_alone(scene):
    """A fired order still in service (not deleted) is a table mid-meal."""
    inv = _fired(scene, number="KK-T2-2026-0000560", deleted=False)
    call_command("repair_paid_held_invoices", "--served-no-payment", "--apply",
                 stdout=StringIO())
    inv.refresh_from_db()
    assert inv.is_held is True, "a table still eating must not be booked as a sale"


def test_default_mode_does_not_touch_served_no_payment(scene):
    """Without the flag the behaviour is unchanged — opt-in only."""
    inv = _fired(scene, number="KK-T2-2026-0000544")
    call_command("repair_paid_held_invoices", "--apply", stdout=StringIO())
    inv.refresh_from_db()
    assert inv.deleted_at is not None
