"""The nightly sweep that keeps the Open orders screen honest.

close_paid_order() can close a stranded order, but a management command only
helps when somebody runs it — and nobody runs one nightly. So stale orders
kept accumulating on every till: 164 at TDCP across six days, of which only
the current day's 11 were real tables.

The sweep must be aggressive enough to clear yesterday and earlier, and
conservative enough that it never closes a table that is still eating.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.hotel.models import FolioInvoice, GuestFolio, Room
from apps.restaurant.services import open_orders_qs
from apps.restaurant.tasks import close_stale_open_orders
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


def _order(scene, *, number, days_ago=1, status="sent_to_kitchen", total="1000"):
    tenant, branch, terminal, user = scene
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=user,
        client_uuid=uuid.uuid4(), local_invoice_number=number,
        invoice_date=timezone.localdate() - dt.timedelta(days=days_ago),
        status="pending_sync",
        is_held=True, order_type="dine_in", order_status=status,
        subtotal=Decimal(total), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal(total),
        paid_total=Decimal("0"), change_given=Decimal("0"),
    )


def test_closes_yesterdays_fired_order_and_records_the_money(scene):
    tenant, _, _, _ = scene
    inv = _order(scene, number="KK-T2-2026-0000800", days_ago=1)

    result = close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.is_held is False
    assert not open_orders_qs(tenant.id).filter(pk=inv.pk).exists()
    # The sale must not be left unpaid on the server.
    assert inv.payments.filter(status="completed").count() == 1
    assert inv.paid_total == Decimal("1000")
    assert result["closed"] == 1


def test_leaves_todays_live_table_alone(scene):
    """A party still eating tonight must never be closed under them."""
    tenant, _, _, _ = scene
    inv = _order(scene, number="KK-T2-2026-0000801", days_ago=0)

    result = close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.is_held is True
    assert open_orders_qs(tenant.id).filter(pk=inv.pk).exists()
    assert inv.payments.count() == 0
    assert result["closed"] == 0


@pytest.mark.parametrize("status", ["sent_to_kitchen", "ready", "served"])
def test_closes_every_state_that_means_the_kitchen_cooked_it(scene, status):
    inv = _order(scene, number=f"KK-T2-2026-00008-{status[:4]}",
                 days_ago=2, status=status)

    close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.is_held is False, f"{status} is a cooked order and must close"


def test_leaves_an_unfired_draft_alone(scene):
    """order_status 'open' = saved but never sent to the kitchen: not a sale."""
    inv = _order(scene, number="KK-T2-2026-0000802", days_ago=3, status="open")

    close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.is_held is True
    assert inv.payments.count() == 0, "an abandoned draft must not invent revenue"


def test_leaves_an_already_paid_order_alone(scene):
    tenant, _, _, _ = scene
    inv = _order(scene, number="KK-T2-2026-0000803", days_ago=2)
    Payment.objects.create(
        tenant=tenant, invoice=inv, payment_method="card",
        amount=Decimal("1000"), status="completed",
    )

    close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.payments.count() == 1
    assert inv.payments.first().payment_method == "card", "must not overwrite tender"


def test_leaves_a_folio_charge_alone(scene):
    """A room-service charge is internal to a stay; checkout settles it."""
    tenant, branch, _, user = scene
    inv = _order(scene, number="KK-T2-2026-0000804", days_ago=2)
    room = Room.objects.create(
        tenant=tenant, branch=branch, room_number="101", room_type="Standard",
        nightly_base=Decimal("5000"), nightly_tax=Decimal("800"),
    )
    folio = GuestFolio.objects.create(
        tenant=tenant, branch=branch, folio_number="KK-F-2026-0001",
        guest_name="G", guest_cnic="35201-1234567-1", guest_phone="03001234567",
        room=room, check_in=timezone.now(), opened_by=user, status="open",
    )
    FolioInvoice.objects.create(
        tenant=tenant, folio=folio, invoice=inv, kind="restaurant", room=room,
    )

    close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.is_held is True, "a folio charge must stay internal to the stay"
    assert inv.payments.count() == 0


def test_is_idempotent(scene):
    inv = _order(scene, number="KK-T2-2026-0000805", days_ago=2)

    close_stale_open_orders()
    second = close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.payments.count() == 1, "must never double-pay an order"
    assert second["closed"] == 0


def test_zero_value_order_is_skipped(scene):
    """An empty shell carries no sale, so there is nothing to settle."""
    inv = _order(scene, number="KK-T2-2026-0000806", days_ago=2, total="0")

    close_stale_open_orders()

    inv.refresh_from_db()
    assert inv.is_held is True
    assert inv.payments.count() == 0


def test_sweeps_every_terminal_not_just_one(scene):
    """The bug report was 'fix it for all kind of terminals'."""
    tenant, branch, _, user = scene
    other = Terminal.objects.create(
        tenant=tenant, branch=branch, name="T3",
        device_fingerprint=uuid.uuid4().hex,
    )
    a = _order(scene, number="KK-T2-2026-0000807", days_ago=1)
    b = _order(scene, number="KK-T3-2026-0000808", days_ago=1)
    b.terminal = other
    b.save(update_fields=["terminal"])

    result = close_stale_open_orders()

    a.refresh_from_db(); b.refresh_from_db()
    assert a.is_held is False and b.is_held is False
    assert result["closed"] == 2


def test_older_than_days_window_is_respected(scene):
    """A longer grace period leaves recent days on the screen."""
    yday = _order(scene, number="KK-T2-2026-0000809", days_ago=1)
    old = _order(scene, number="KK-T2-2026-0000810", days_ago=5)

    close_stale_open_orders(older_than_days=3)

    yday.refresh_from_db(); old.refresh_from_db()
    assert yday.is_held is True, "inside the grace window"
    assert old.is_held is False, "beyond the grace window"
