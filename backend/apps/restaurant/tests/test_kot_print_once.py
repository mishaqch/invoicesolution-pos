"""KOT must print exactly once per line, and a re-fire must send only NEW items.

Both reported faults share ONE root cause: the firing till printed its own
slip but never acked it, so kot_printed_at stayed NULL forever.

  1. Duplicate slips — the KOT relay polls for lines that are
     (sent_to_kitchen AND kot_printed_at IS NULL). An unacked line is still
     "unprinted", so the relay printed a SECOND slip at the kitchen.

  2. Re-fire reprints everything — upsert_open_order carries kot_printed_at
     across its delete+recreate to work out which lines are new. With every
     line unprinted, adding 2 items to a fired order re-sent the WHOLE order.

Production evidence at the time: 2460 sale_items with sent_to_kitchen=true
and kot_printed_at NULL, and zero mark-printed calls in the audit log.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import Product, UnitOfMeasure
from apps.restaurant import services
from apps.restaurant.views import _order_detail_payload, _kot_relay_payload
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
    uom = UnitOfMeasure.objects.get(code="PCS")
    biryani = Product.objects.create(
        tenant=tenant, name="Biryani", sku=uuid.uuid4().hex[:8], uom=uom,
        sale_price=Decimal("500"), cost_price=Decimal("200"),
    )
    tea = Product.objects.create(
        tenant=tenant, name="Tea", sku=uuid.uuid4().hex[:8], uom=uom,
        sale_price=Decimal("100"), cost_price=Decimal("40"),
    )
    return tenant, branch, terminal, user, biryani, tea


def _line(product, qty="1", sent=False):
    return {
        "product": str(product.id), "quantity": qty,
        "unit_price": str(product.sale_price), "tax_rate": "0",
        "is_taxable": False, "modifiers": [], "sent_to_kitchen": sent,
    }


def _fire(scene, cart_lines, client_uuid):
    tenant, branch, terminal, user, *_ = scene
    return services.upsert_open_order(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=user,
        payload={
            "client_uuid": str(client_uuid), "cart_lines": cart_lines,
            "order_type": "dine_in", "fire": True,
        },
    )


def test_detail_payload_exposes_line_id_and_print_state(scene):
    """The till cannot ack a print without the line ids — that omission is
    what left kot_printed_at NULL forever."""
    _, _, _, _, biryani, _ = scene
    inv = _fire(scene, [_line(biryani)], uuid.uuid4())

    payload = _order_detail_payload(inv)

    line = payload["cart_lines"][0]
    assert "id" in line, "cart_lines must carry the SaleItem id so the till can ack"
    assert line["kot_printed"] is False
    assert uuid.UUID(line["id"])


def test_acked_lines_leave_the_unprinted_feed(scene):
    """Issue 2: after the firing till acks, the relay must see nothing —
    otherwise it prints a second slip."""
    _, _, _, _, biryani, _ = scene
    inv = _fire(scene, [_line(biryani)], uuid.uuid4())

    assert len(_kot_relay_payload(inv)["items"]) == 1, "relay should see it before the ack"

    # The till prints and acks (what fire.ts now does via markKotPrinted).
    from django.utils import timezone
    SaleItem.objects.filter(invoice=inv, kot_printed_at__isnull=True).update(
        kot_printed_at=timezone.now(),
    )

    assert _kot_relay_payload(inv)["items"] == [], "relay would print a DUPLICATE slip"


def test_refire_sends_only_the_new_items(scene):
    """Issue 1: add 2 items to an order already sent to the kitchen.

    Only the new lines may reach the kitchen, under the SAME order number.
    """
    _, _, _, _, biryani, tea = scene
    cu = uuid.uuid4()

    # Course 1: biryani, fired and printed.
    inv = _fire(scene, [_line(biryani)], cu)
    order_number = inv.local_invoice_number
    from django.utils import timezone
    SaleItem.objects.filter(invoice=inv).update(kot_printed_at=timezone.now())

    # Course 2: cashier adds tea to the SAME order and fires again. The client
    # echoes sent_to_kitchen=True for the line already fired.
    inv = _fire(scene, [_line(biryani, sent=True), _line(tea)], cu)

    assert inv.local_invoice_number == order_number, "order number must not change"

    feed = _kot_relay_payload(inv)
    names = [i["product_name"] for i in feed["items"]]
    assert names == ["Tea"], f"only the NEW item may print; got {names}"
    assert feed["is_additional"] is True, "ticket must read ADDITIONAL ORDER"


def test_refire_without_ack_reprints_everything(scene):
    """The failure mode itself: with kot_printed_at never set, a re-fire
    re-sends the whole order. This is what the kitchen was seeing."""
    _, _, _, _, biryani, tea = scene
    cu = uuid.uuid4()

    inv = _fire(scene, [_line(biryani)], cu)
    # NO ack here -- the old behaviour.
    inv = _fire(scene, [_line(biryani, sent=True), _line(tea)], cu)

    names = sorted(i["product_name"] for i in _kot_relay_payload(inv)["items"])
    assert names == ["Biryani", "Tea"], (
        "without an ack the whole order reprints -- this documents WHY the "
        "mark-printed ack in fire.ts is required"
    )
