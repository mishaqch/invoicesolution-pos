"""KOT relay + waiter-tablet handoff.

A printer-less waiter tablet fires an order; the branch's Electron terminal polls
`kds/unprinted/`, prints the KOT, then POSTs `mark-printed/`. These tests pin the
guarantees that make that reliable and safe:

- unprinted feed returns only fired, not-yet-printed, non-cancelled food lines,
  excluding Rooms (waiter takes menu orders only);
- mark-printed is idempotent (print-exactly-once across a retry / two terminals);
- an incremental "course 2" fire relays only the newly-fired lines;
- a cashier till can see + resume an order a waiter tablet fired (handoff), while
  ordinary tills stay private to each other;
- the waiter role can take/fire orders but cannot charge.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.restaurant import services
from apps.restaurant.services import open_orders_qs
from apps.restaurant.views import (
    KdsUnprintedView,
    MarkKotPrintedView,
    OpenOrderView,
)
from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def scene(db):
    from apps.catalog.models import Category, Product, UnitOfMeasure

    uom, _ = UnitOfMeasure.objects.get_or_create(
        code="NOS", defaults={"name_en": "Numbers, pieces, units"},
    )

    tenant = Tenant.objects.create(
        business_name="Resort", ntn=f"N{uuid.uuid4().hex[:8]}",
        business_type="sole_proprietor", province="PUNJAB",
        fbr_connection_type="none",
    )
    branch = Branch.objects.create(tenant=tenant, name="Main", code="M", address="x")
    # Shared waiter tablet terminal (fires only, never charges).
    tablet = Terminal.objects.create(
        tenant=tenant, branch=branch, name="Waiter tablets",
        device_fingerprint=uuid.uuid4().hex, is_order_taking_only=True,
    )
    # A cashier till.
    till = Terminal.objects.create(
        tenant=tenant, branch=branch, name="Till 1",
        device_fingerprint=uuid.uuid4().hex,
    )
    cashier = User.objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test", password="x", full_name="C",
    )
    TenantMembership.objects.create(tenant=tenant, user=cashier, role="cashier")

    food_cat = Category.objects.create(tenant=tenant, name="Main Course", slug="main-course")
    rooms_cat = Category.objects.create(tenant=tenant, name="Rooms", slug="rooms")
    burger = Product.objects.create(
        tenant=tenant, name="Burger", sku="BURG", category=food_cat, uom=uom,
        sale_price=Decimal("500"), cost_price=Decimal("200"),
    )
    room = Product.objects.create(
        tenant=tenant, name="Deluxe Room", sku="ROOM", category=rooms_cat, uom=uom,
        sale_price=Decimal("9000"), cost_price=Decimal("0"),
    )
    return dict(
        tenant=tenant, branch=branch, tablet=tablet, till=till,
        cashier=cashier, burger=burger, room=room,
    )


def _order(scene, terminal, *, fired=True):
    inv = Invoice.objects.create(
        tenant=scene["tenant"], branch=scene["branch"], terminal=terminal,
        cashier=scene["cashier"], local_invoice_number=f"ORD-{uuid.uuid4().hex[:6]}",
        invoice_date=dt.date.today(), status="pending_sync", is_held=True,
        order_status="sent_to_kitchen" if fired else "open", order_type="dine_in",
        grand_total=Decimal("500"), client_uuid=uuid.uuid4(),
        kitchen_sent_at=timezone.now() if fired else None,
    )
    return inv


def _line(inv, product, *, sent, qty="1", cancelled=False, printed=False):
    return SaleItem.objects.create(
        invoice=inv, line_number=inv.items.count() + 1, product=product,
        product_name=product.name, product_sku=product.sku,
        quantity=Decimal(qty), unit_price=product.sale_price,
        cost_price=product.cost_price, line_total=product.sale_price,
        sent_to_kitchen=sent, is_cancelled=cancelled,
        kot_printed_at=timezone.now() if printed else None,
    )


# ---- unprinted feed -------------------------------------------------------

def _unprinted(scene):
    factory = APIRequestFactory()
    req = factory.get(f"/api/restaurant/kds/unprinted/?branch={scene['branch'].id}")
    force_authenticate(req, user=scene["cashier"])
    req.tenant_id = str(scene["tenant"].id)
    resp = KdsUnprintedView.as_view()(req)
    assert resp.status_code == 200, resp.data
    return resp.data["orders"]


def test_unprinted_lists_fired_unprinted_food_lines(scene):
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True)

    orders = _unprinted(scene)
    assert len(orders) == 1
    assert orders[0]["id"] == str(inv.id)
    assert [i["product_name"] for i in orders[0]["items"]] == ["Burger"]
    assert orders[0]["is_additional"] is False


def test_unprinted_excludes_rooms(scene):
    """A waiter takes menu orders only — a Rooms line must never hit the kitchen."""
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True)
    _line(inv, scene["room"], sent=True)

    orders = _unprinted(scene)
    assert len(orders) == 1
    names = [i["product_name"] for i in orders[0]["items"]]
    assert names == ["Burger"]  # room excluded
    assert str(scene["room"].id) not in " ".join(orders[0]["item_ids"])


def test_unprinted_order_with_only_rooms_is_dropped(scene):
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["room"], sent=True)
    assert _unprinted(scene) == []


def test_unprinted_excludes_already_printed_and_cancelled(scene):
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True, printed=True)  # already printed
    _line(inv, scene["burger"], sent=True, cancelled=True)  # cancelled
    assert _unprinted(scene) == []


def test_unprinted_incremental_course_flags_additional(scene):
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True, printed=True)  # course 1 already printed
    course2 = _line(inv, scene["burger"], sent=True)  # course 2 newly fired

    orders = _unprinted(scene)
    assert len(orders) == 1
    assert orders[0]["is_additional"] is True
    assert orders[0]["item_ids"] == [str(course2.id)]


# ---- mark-printed idempotency --------------------------------------------

def _mark_printed(scene, inv, item_ids):
    factory = APIRequestFactory()
    req = factory.post(
        f"/api/restaurant/orders/{inv.id}/mark-printed/",
        {"item_ids": item_ids}, format="json",
    )
    force_authenticate(req, user=scene["cashier"])
    req.tenant_id = str(scene["tenant"].id)
    return MarkKotPrintedView.as_view()(req, pk=str(inv.id))


def test_mark_printed_stamps_lines_and_is_idempotent(scene):
    inv = _order(scene, scene["tablet"])
    line = _line(inv, scene["burger"], sent=True)

    r1 = _mark_printed(scene, inv, [str(line.id)])
    assert r1.status_code == 200
    assert r1.data["marked"] == 1
    line.refresh_from_db()
    assert line.kot_printed_at is not None

    # Retry (lost ack) or a second terminal racing: no double print, no error.
    r2 = _mark_printed(scene, inv, [str(line.id)])
    assert r2.status_code == 200
    assert r2.data["marked"] == 0

    # And it's gone from the unprinted feed.
    assert _unprinted(scene) == []


def test_mark_printed_only_touches_named_lines(scene):
    inv = _order(scene, scene["tablet"])
    a = _line(inv, scene["burger"], sent=True)
    b = _line(inv, scene["burger"], sent=True)
    _mark_printed(scene, inv, [str(a.id)])
    a.refresh_from_db(); b.refresh_from_db()
    assert a.kot_printed_at is not None
    assert b.kot_printed_at is None


# ---- device auth (relay works with no cashier logged in) ------------------

def test_unprinted_via_device_auth_no_login(scene):
    """The relay must print without a cashier login — it authenticates as a
    PAIRED DEVICE (terminal_id + device_fingerprint), NOT a bearer token. This is
    the fix for 'kitchen printing silently dead until someone signs into the
    till'."""
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True)

    factory = APIRequestFactory()
    # No force_authenticate, no req.tenant_id — pure device credentials, exactly
    # what a paired-but-not-logged-in till sends.
    req = factory.get(
        f"/api/restaurant/kds/unprinted/?branch={scene['branch'].id}"
        f"&terminal_id={scene['till'].id}"
        f"&device_fingerprint={scene['till'].device_fingerprint}"
    )
    resp = KdsUnprintedView.as_view()(req)
    assert resp.status_code == 200, resp.data
    assert len(resp.data["orders"]) == 1


def test_unprinted_device_auth_rejects_bad_fingerprint(scene):
    factory = APIRequestFactory()
    req = factory.get(
        f"/api/restaurant/kds/unprinted/?branch={scene['branch'].id}"
        f"&terminal_id={scene['till'].id}&device_fingerprint=wrong"
    )
    resp = KdsUnprintedView.as_view()(req)
    assert resp.status_code in (401, 403), resp.status_code


def test_mark_printed_via_device_auth_no_login(scene):
    inv = _order(scene, scene["tablet"])
    line = _line(inv, scene["burger"], sent=True)
    factory = APIRequestFactory()
    req = factory.post(
        f"/api/restaurant/orders/{inv.id}/mark-printed/",
        {
            "item_ids": [str(line.id)],
            "terminal_id": str(scene["till"].id),
            "device_fingerprint": scene["till"].device_fingerprint,
        },
        format="json",
    )
    resp = MarkKotPrintedView.as_view()(req, pk=str(inv.id))
    assert resp.status_code == 200, resp.data
    assert resp.data["marked"] == 1


# ---- cashier handoff ------------------------------------------------------

def test_till_sees_waiter_tablet_order_in_open_list(scene):
    """A waiter-fired order must appear on the branch's cashier till so it can be
    charged — the tablet has no till of its own to close it."""
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True)

    till_orders = list(open_orders_qs(
        scene["tenant"].id, branch_id=str(scene["branch"].id),
        terminal_id=str(scene["till"].id),
    ))
    assert inv.id in {o.id for o in till_orders}


def test_till_resume_allows_waiter_tablet_order(scene):
    inv = _order(scene, scene["tablet"])
    _line(inv, scene["burger"], sent=True)
    factory = APIRequestFactory()
    req = factory.get(f"/api/restaurant/orders/?id={inv.id}&terminal={scene['till'].id}")
    force_authenticate(req, user=scene["cashier"])
    req.tenant_id = str(scene["tenant"].id)
    resp = OpenOrderView.as_view()(req)
    assert resp.status_code == 200
    assert resp.data["id"] == str(inv.id)


def test_till_resume_still_rejects_other_plain_till_order(scene):
    """The handoff exception is narrow: a NON-order-taking till's order stays
    private to it."""
    other_till = Terminal.objects.create(
        tenant=scene["tenant"], branch=scene["branch"], name="Till 2",
        device_fingerprint=uuid.uuid4().hex,
    )
    inv = _order(scene, other_till)
    factory = APIRequestFactory()
    req = factory.get(f"/api/restaurant/orders/?id={inv.id}&terminal={scene['till'].id}")
    force_authenticate(req, user=scene["cashier"])
    req.tenant_id = str(scene["tenant"].id)
    resp = OpenOrderView.as_view()(req)
    assert resp.status_code == 404


# ---- safety guards on upsert ---------------------------------------------

def test_upsert_refuses_already_charged_order(scene):
    """A late/duplicate re-fire must never reopen a charged sale."""
    from rest_framework.exceptions import ValidationError

    cu = uuid.uuid4()
    Invoice.objects.create(
        tenant=scene["tenant"], branch=scene["branch"], terminal=scene["till"],
        cashier=scene["cashier"], local_invoice_number="INV-1",
        invoice_date=dt.date.today(), status="submitted", is_held=False,
        grand_total=Decimal("500"), client_uuid=cu,
    )
    with pytest.raises(ValidationError):
        services.upsert_open_order(
            tenant_id=scene["tenant"].id, branch=scene["branch"],
            terminal=scene["tablet"], cashier=scene["cashier"],
            payload={"client_uuid": str(cu), "cart_lines": [], "fire": True},
        )


def test_upsert_conflict_on_stale_expected_updated_at(scene):
    from rest_framework.exceptions import APIException

    inv = _order(scene, scene["tablet"], fired=False)
    cu = inv.client_uuid
    stale = (inv.updated_at - dt.timedelta(seconds=60)).isoformat()
    with pytest.raises(APIException) as exc:
        services.upsert_open_order(
            tenant_id=scene["tenant"].id, branch=scene["branch"],
            terminal=scene["tablet"], cashier=scene["cashier"],
            payload={
                "client_uuid": str(cu), "cart_lines": [],
                "fire": False, "expected_updated_at": stale,
            },
        )
    assert exc.value.status_code == 409


# ---- fire actually queues the KOT (regression: smoke test 2026-09-03) ------

def _fire_via_service(scene, cart_lines, *, fire=True, client_uuid=None):
    cu = client_uuid or str(uuid.uuid4())
    inv = services.upsert_open_order(
        tenant_id=scene["tenant"].id, branch=scene["branch"],
        terminal=scene["tablet"], cashier=scene["cashier"],
        payload={
            "client_uuid": cu, "order_type": "dine_in", "fire": fire,
            "cart_lines": cart_lines,
        },
    )
    return inv, cu


def test_fire_marks_lines_sent_even_when_client_echoes_false(scene):
    """THE bug the smoke test caught: the tablet echoes sent_to_kitchen=false on a
    brand-new line, but firing MUST put it on the kitchen queue anyway — otherwise
    the KOT relay (which reads sent_to_kitchen) never prints it. A fire sends every
    line, regardless of the client's per-line echo."""
    inv, _ = _fire_via_service(scene, [
        {"product": str(scene["burger"].id), "quantity": "2", "unit_price": "500",
         "tax_rate": "16", "is_taxable": True, "sent_to_kitchen": False},
    ])
    line = inv.items.get()
    assert line.sent_to_kitchen is True
    assert line.kot_printed_at is None  # queued, not yet printed


def test_refire_preserves_printed_state_prints_only_new_line(scene):
    """A course-2 re-fire must NOT reprint an already-printed line. The delete+
    recreate on upsert would wipe kot_printed_at; the service carries it across by
    content signature onto the client's already-sent lines, so only the genuinely
    new line stays unprinted."""
    # Course 1: fire one burger, then the relay prints it.
    inv, cu = _fire_via_service(scene, [
        {"product": str(scene["burger"].id), "quantity": "1", "unit_price": "500",
         "tax_rate": "16", "is_taxable": True, "sent_to_kitchen": False},
    ])
    printed_line = inv.items.get()
    printed_line.kot_printed_at = timezone.now()
    printed_line.save(update_fields=["kot_printed_at"])

    # Course 2: same client_uuid, echo the printed burger as already-sent, add a
    # NEW burger line (same product) marked not-yet-sent.
    inv2, _ = _fire_via_service(scene, [
        {"product": str(scene["burger"].id), "quantity": "1", "unit_price": "500",
         "tax_rate": "16", "is_taxable": True, "sent_to_kitchen": True},
        {"product": str(scene["burger"].id), "quantity": "1", "unit_price": "500",
         "tax_rate": "16", "is_taxable": True, "sent_to_kitchen": False},
    ], client_uuid=cu)

    lines = list(inv2.items.order_by("line_number"))
    assert len(lines) == 2
    # Exactly one line already-printed (course 1 carried across), one unprinted.
    printed = [l for l in lines if l.kot_printed_at is not None]
    unprinted = [l for l in lines if l.kot_printed_at is None]
    assert len(printed) == 1 and len(unprinted) == 1
    # Both are on the kitchen queue (fired), only the new one prints next.
    assert all(l.sent_to_kitchen for l in lines)


# ---- waiter role ----------------------------------------------------------

def test_waiter_role_cannot_charge(scene):
    """The waiter role has no sales.create — checkout must refuse it. Order-taking
    itself is gated only by tenant membership + the restaurant module, so a waiter
    can still fire orders."""
    from apps.accounts.permissions import DEFAULT_ROLE_PERMS

    charge_roles = DEFAULT_ROLE_PERMS.get("sales.create", set())
    assert "waiter" not in charge_roles
    cancel_roles = DEFAULT_ROLE_PERMS.get("sales.cancel.threshold_low", set())
    assert "waiter" not in cancel_roles
