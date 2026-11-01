"""Hotel guest-folio flow — open a stay, add charges, checkout, consolidated bill.

Covers the multi-day resort tab: room nights auto-charged with the FIXED
per-night tax amount, restaurant charges appended, room occupancy flips, and the
consolidated bill sums every charge.
"""

from __future__ import annotations

import datetime as dt
import uuid
from io import StringIO
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product, UnitOfMeasure
from apps.hotel import services
from apps.hotel.models import GuestFolio, Room
from apps.tenants.models import Branch, Terminal, Tenant

pytestmark = pytest.mark.django_db

User_kwargs = dict(full_name="Cashier")


def _setup():
    from django.contrib.auth import get_user_model
    U = get_user_model()
    tenant = Tenant.objects.create(
        business_name="TDCP Resort", ntn=str(uuid.uuid4().int)[:7],
        business_type="sole_proprietor", business_mode="pos",
        vertical="restaurant", fbr_connection_type="none",
    )
    branch = Branch.objects.create(tenant=tenant, name="Kallar Kahar", code="KK")
    terminal = Terminal.objects.create(tenant=tenant, branch=branch, name="Reception")
    cashier = U.objects.create(email=f"c-{uuid.uuid4().hex[:8]}@t.pk", full_name="Cashier")
    uom_night, _ = UnitOfMeasure.objects.get_or_create(
        code="NIGHT", defaults={"name_en": "Night"},
    )
    uom_pcs, _ = UnitOfMeasure.objects.get_or_create(
        code="PCS", defaults={"name_en": "Pieces"},
    )
    cat = Category.objects.create(tenant=tenant, name="Rooms", slug="rooms")
    food_cat = Category.objects.create(tenant=tenant, name="Food", slug="food")

    vip_product = Product.objects.create(
        tenant=tenant, sku="ROOM-VIP", name="VIP Room / night",
        category=cat, uom=uom_night, sale_price=Decimal("8820"),
        cost_price=Decimal("0"), is_taxable=True,
    )
    room = Room.objects.create(
        tenant=tenant, branch=branch, room_number="VIP-1", room_type="VIP",
        nightly_base=Decimal("8820"), nightly_tax=Decimal("1680"),
        product=vip_product, status="available",
    )
    biryani = Product.objects.create(
        tenant=tenant, sku="BIRYANI", name="Chicken Biryani",
        category=food_cat, uom=uom_pcs, sale_price=Decimal("500"),
        cost_price=Decimal("0"), is_taxable=True,
    )
    return tenant, branch, terminal, cashier, room, biryani


def test_open_stay_auto_charges_room_with_fixed_tax():
    tenant, branch, terminal, cashier, room, _ = _setup()
    check_in = timezone.make_aware(dt.datetime(2026, 6, 30, 18, 0))
    check_out = timezone.make_aware(dt.datetime(2026, 7, 10, 11, 0))

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali Khan", guest_cnic="3520112345671",
        guest_phone="03001234567", room=room,
        check_in=check_in, expected_check_out=check_out,
    )
    # 10 nights (Jun 30 -> Jul 10).
    assert folio.nights == 10
    assert folio.status == "open"
    # Room is now occupied.
    room.refresh_from_db()
    assert room.status == "occupied"

    bill = services.consolidated_bill(folio)
    # Room charge: 10 nights × base 8820 = 88,200 + fixed tax 1680×10 = 16,800.
    assert bill["subtotal"] == "88200.0000"
    assert bill["tax_total"] == "16800.0000"
    assert bill["grand_total"] == "105000.0000"


def test_add_restaurant_charge_and_consolidate():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room,
        check_in=timezone.make_aware(dt.datetime(2026, 6, 30, 18, 0)),
        expected_check_out=timezone.make_aware(dt.datetime(2026, 7, 1, 11, 0)),  # 1 night
    )
    # Add a restaurant charge: 2 × Biryani @ 500, 16% tax.
    services.add_charge(
        folio=folio, terminal=terminal, cashier=cashier, cash_session=None,
        cart_lines=[{
            "product": str(biryani.id), "quantity": "2", "unit_price": "500",
            "tax_rate": "16", "is_taxable": True, "discount_amount": "0",
        }],
        kind="restaurant",
    )
    bill = services.consolidated_bill(folio)
    # Room: base 8820 + tax 1680 = 10500.  Food: 1000 + 160 = 1160.
    assert bill["subtotal"] == "9820.0000"       # 8820 + 1000
    assert bill["tax_total"] == "1840.0000"       # 1680 + 160
    assert bill["grand_total"] == "11660.0000"    # 10500 + 1160
    # Two charge entries (room + restaurant).
    assert len(folio.charges.all()) == 2


def test_checkout_frees_room_and_closes_folio():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room,
        check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )
    assert folio.status == "closed"
    assert folio.check_out is not None
    room.refresh_from_db()
    assert room.status == "available"
    bill = services.consolidated_bill(folio)
    assert bill["paid_total"] == "10500.0000"
    assert bill["balance"] == "0.0000"


def test_cannot_open_occupied_room():
    from django.core.exceptions import ValidationError
    tenant, branch, terminal, cashier, room, _ = _setup()
    services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="A", guest_cnic="1", guest_phone="0",
        room=room, check_in=timezone.now(),
    )
    with pytest.raises(ValidationError):
        services.open_stay(
            tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
            cash_session=None, guest_name="B", guest_cnic="2", guest_phone="0",
            room=room, check_in=timezone.now(),
        )


def test_void_item_drops_total():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room,
        check_in=timezone.make_aware(dt.datetime(2026, 6, 30, 18, 0)),
        expected_check_out=timezone.make_aware(dt.datetime(2026, 7, 1, 11, 0)),  # 1 night
    )
    charge = services.add_charge(
        folio=folio, terminal=terminal, cashier=cashier, cash_session=None,
        cart_lines=[{"product": str(biryani.id), "quantity": "2", "unit_price": "500",
                     "tax_rate": "16", "is_taxable": True, "discount_amount": "0"}],
        kind="restaurant",
    )
    before = services.consolidated_bill(folio)
    assert before["grand_total"] == "11660.0000"  # room 10500 + food 1160
    item_id = charge.invoice.items.first().id
    services.void_item(folio=folio, charge=charge, sale_item_id=item_id, user=cashier)
    after = services.consolidated_bill(folio)
    # Food charge now empty -> only the room remains.
    assert after["grand_total"] == "10500.0000"
    # The (now-empty) food charge is skipped; only the room day shows.
    total_charges = sum(len(d["charges"]) for d in after["days"])
    assert total_charges == 1


def test_void_whole_charge():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    charge = services.add_charge(
        folio=folio, terminal=terminal, cashier=cashier, cash_session=None,
        cart_lines=[{"product": str(biryani.id), "quantity": "1", "unit_price": "500",
                     "tax_rate": "16", "is_taxable": True, "discount_amount": "0"}],
        kind="restaurant",
    )
    services.void_charge(folio=folio, charge=charge, user=cashier)
    after = services.consolidated_bill(folio)
    assert after["grand_total"] == "10500.0000"  # only the room


def test_cannot_void_room_charge():
    from django.core.exceptions import ValidationError
    from apps.hotel.models import FolioInvoice
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room, check_in=timezone.now(),
    )
    room_charge = FolioInvoice.objects.get(folio=folio, kind="room")
    with pytest.raises(ValidationError):
        services.void_charge(folio=folio, charge=room_charge, user=cashier)


def test_multi_room_one_guest():
    """Ali books TWO rooms under one folio; each room auto-charges its nights,
    and the consolidated bill sums both rooms into one grand total."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    # A second room (Deluxe).
    from apps.catalog.models import Product, Category, UnitOfMeasure
    uom_night = UnitOfMeasure.objects.get(code="NIGHT")
    cat = Category.objects.get(tenant=tenant, slug="rooms")
    dlx_product = Product.objects.create(
        tenant=tenant, sku="ROOM-DLX", name="Deluxe Room / night",
        category=cat, uom=uom_night, sale_price=Decimal("6300"),
        cost_price=Decimal("0"), is_taxable=True,
    )
    room2 = Room.objects.create(
        tenant=tenant, branch=branch, room_number="DLX-1", room_type="Deluxe",
        nightly_base=Decimal("6300"), nightly_tax=Decimal("1200"),
        product=dlx_product, status="available",
    )
    ci = timezone.make_aware(dt.datetime(2026, 6, 30, 15, 0))
    co = timezone.make_aware(dt.datetime(2026, 7, 2, 11, 0))  # 2 nights

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali Ahmad", guest_cnic="1", guest_phone="0300",
        rooms=[{"room": room}, {"room": room2}],
        check_in=ci, expected_check_out=co,
    )
    bill = services.consolidated_bill(folio)
    # VIP 2 nights: (8820+1680)*2 = 21000.  Deluxe 2 nights: (6300+1200)*2 = 15000.
    assert bill["grand_total"] == "36000.0000"
    assert len(bill["rooms"]) == 2
    # Both rooms now occupied.
    room.refresh_from_db(); room2.refresh_from_db()
    assert room.status == "occupied" and room2.status == "occupied"

    # Checkout frees BOTH rooms.
    services.checkout_stay(folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "36000"}])
    room.refresh_from_db(); room2.refresh_from_db()
    assert room.status == "available" and room2.status == "available"


def _second_room(tenant, branch):
    """A Deluxe room + product for multi-room / add-room tests."""
    from apps.catalog.models import Category, Product, UnitOfMeasure
    uom_night = UnitOfMeasure.objects.get(code="NIGHT")
    cat = Category.objects.get(tenant=tenant, slug="rooms")
    dlx_product = Product.objects.create(
        tenant=tenant, sku="ROOM-DLX", name="Deluxe Room / night",
        category=cat, uom=uom_night, sale_price=Decimal("6300"),
        cost_price=Decimal("0"), is_taxable=True,
    )
    return Room.objects.create(
        tenant=tenant, branch=branch, room_number="DLX-1", room_type="Deluxe",
        nightly_base=Decimal("6300"), nightly_tax=Decimal("1200"),
        product=dlx_product, status="available",
    )


# --- Edit / update stay -----------------------------------------------------

def test_update_stay_edits_guest_details():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali Khan", guest_cnic="1", guest_phone="0300",
        room=room,
    )
    services.update_stay(
        folio=folio,
        fields={"guest_name": "Ali Ahmad Khan", "guest_phone": "03005066442",
                "guest_email": "ali@example.com"},
        user=cashier,
    )
    folio.refresh_from_db()
    assert folio.guest_name == "Ali Ahmad Khan"
    assert folio.guest_phone == "03005066442"
    assert folio.guest_email == "ali@example.com"


def test_update_stay_dates_reprices_room_nights():
    tenant, branch, terminal, cashier, room, _ = _setup()
    ci = timezone.make_aware(dt.datetime(2026, 6, 30, 15, 0))
    co1 = timezone.make_aware(dt.datetime(2026, 7, 2, 11, 0))   # 2 nights
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room, check_in=ci, expected_check_out=co1,
    )
    assert services.consolidated_bill(folio)["grand_total"] == "21000.0000"  # 10500*2

    co2 = timezone.make_aware(dt.datetime(2026, 7, 4, 11, 0))   # 4 nights
    services.update_stay(
        folio=folio, fields={}, check_in=ci, expected_check_out=co2,
        terminal=terminal, cashier=cashier, cash_session=None, user=cashier,
    )
    folio.refresh_from_db()
    assert folio.nights == 4
    # Room re-priced to 4 nights: 10500 * 4 = 42000.
    assert services.consolidated_bill(folio)["grand_total"] == "42000.0000"


def test_cannot_update_closed_stay():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room,
    )
    services.checkout_stay(folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}])
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        services.update_stay(folio=folio, fields={"guest_name": "X"}, user=cashier)


# --- Add / remove room ------------------------------------------------------

def test_add_room_to_stay():
    tenant, branch, terminal, cashier, room, _ = _setup()
    room2 = _second_room(tenant, branch)
    ci = timezone.make_aware(dt.datetime(2026, 6, 30, 15, 0))
    co = timezone.make_aware(dt.datetime(2026, 7, 2, 11, 0))  # 2 nights
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room, check_in=ci, expected_check_out=co,
    )
    assert services.consolidated_bill(folio)["grand_total"] == "21000.0000"  # VIP 2n

    services.add_room_to_stay(
        folio=folio, room=room2, terminal=terminal, cashier=cashier,
        cash_session=None, user=cashier,
    )
    room2.refresh_from_db()
    assert room2.status == "occupied"
    # + Deluxe 2 nights (7500*2 = 15000) → 36000.
    assert services.consolidated_bill(folio)["grand_total"] == "36000.0000"


def test_remove_room_from_stay_frees_room_and_drops_total():
    tenant, branch, terminal, cashier, room, _ = _setup()
    room2 = _second_room(tenant, branch)
    ci = timezone.make_aware(dt.datetime(2026, 6, 30, 15, 0))
    co = timezone.make_aware(dt.datetime(2026, 7, 2, 11, 0))  # 2 nights
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        rooms=[{"room": room}, {"room": room2}], check_in=ci, expected_check_out=co,
    )
    assert services.consolidated_bill(folio)["grand_total"] == "36000.0000"

    services.remove_room_from_stay(folio=folio, room=room2, user=cashier)
    room2.refresh_from_db()
    assert room2.status == "available"
    # Deluxe removed → back to VIP-only 21000.
    assert services.consolidated_bill(folio)["grand_total"] == "21000.0000"


def test_cannot_remove_last_room():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room,
    )
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        services.remove_room_from_stay(folio=folio, room=room, user=cashier)


# --- Cancel stay ------------------------------------------------------------

def test_cancel_stay_voids_charges_and_frees_rooms():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room,
    )
    # A food charge too, to prove everything gets voided.
    services.add_charge(
        folio=folio, terminal=terminal, cashier=cashier, cash_session=None,
        cart_lines=[{"product": str(biryani.id), "quantity": "2",
                     "unit_price": "500", "tax_rate": "16", "is_taxable": True,
                     "discount_amount": "0"}],
        kind="restaurant",
    )
    services.cancel_stay(folio=folio, reason="Customer changed mind", user=cashier)
    folio.refresh_from_db()
    room.refresh_from_db()
    assert folio.status == "cancelled"
    assert room.status == "available"
    # Bill collapses to zero — every charge voided.
    bill = services.consolidated_bill(folio)
    assert bill["grand_total"] == "0.0000"


def test_cannot_cancel_checked_out_stay():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="1", guest_phone="0300",
        room=room,
    )
    services.checkout_stay(folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}])
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        services.cancel_stay(folio=folio, user=cashier)


# --- Standard 12:30 PM PKT checkout + TZ-correct nights (2026-09-04) ----------

def test_checkout_defaults_to_1230pm_pkt():
    """Checkout with NO explicit time must default to the resort's standard
    12:30 PM Asia/Karachi checkout — not the arbitrary click moment."""
    from zoneinfo import ZoneInfo
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )
    local = folio.check_out.astimezone(ZoneInfo("Asia/Karachi"))
    assert (local.hour, local.minute) == (12, 30), local.isoformat()


def test_checkout_honours_explicit_time():
    """An explicit late/early checkout time is respected (override)."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
    )
    explicit = timezone.now() + dt.timedelta(hours=3)
    folio = services.checkout_stay(
        folio=folio, cashier=cashier, check_out=explicit,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )
    assert abs((folio.check_out - explicit).total_seconds()) < 2


def test_open_stay_defaults_expected_checkout_to_1230_next_day():
    from zoneinfo import ZoneInfo
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
    )
    eco = folio.expected_check_out.astimezone(ZoneInfo("Asia/Karachi"))
    assert (eco.hour, eco.minute) == (12, 30), eco.isoformat()


def test_compute_nights_tz_localized_no_off_by_one():
    """A late-evening PKT check-in (still 'yesterday' in UTC) to next-day 12:30
    must count as 1 night, not 2."""
    from zoneinfo import ZoneInfo
    pk = ZoneInfo("Asia/Karachi")
    ci = dt.datetime(2026, 6, 30, 23, 0, tzinfo=pk)   # 23:00 PKT = 18:00 UTC
    co = dt.datetime(2026, 7, 1, 12, 30, tzinfo=pk)   # next day 12:30 PKT
    assert services.compute_nights(ci, co) == 1


def test_release_room_frees_stuck_room():
    """Manager force-release frees a room stuck 'occupied' with no open folio."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    room.status = "occupied"
    room.save(update_fields=["status"])
    services.release_room(room=room, user=cashier)
    room.refresh_from_db()
    assert room.status == "available"


def test_release_room_refuses_when_open_stay():
    """Force-release must REFUSE a room that genuinely has an open stay."""
    from django.core.exceptions import ValidationError
    tenant, branch, terminal, cashier, room, _ = _setup()
    services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
    )
    with pytest.raises(ValidationError):
        services.release_room(room=room, user=cashier)


# --- ONE invoice per stay -------------------------------------------------
# A stay used to produce no invoice of its own. Checkout un-held every FOL-
# charge, so each internal line item (room night, each day's food) surfaced in
# the admin invoice list as if it were a separate sale — 237 rows worth
# PKR 2.0M at TDCP — and the whole settlement was recorded against one
# arbitrary "anchor" room, leaving 26 invoices carrying PKR 321k of payment
# they had not earned.
#
# Now the guest gets ONE real terminal invoice covering room + food, and the
# FOL- charges stay held and internal.

def test_checkout_mints_one_real_invoice_for_the_stay():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )

    inv = folio.settlement_invoice
    assert inv is not None, "the stay must have its own invoice"
    # A REAL terminal number, not a FOL- tag.
    assert not inv.local_invoice_number.startswith("FOL-")
    assert inv.is_held is False
    assert inv.buyer_name == "Ali", "the bill belongs to the guest, not the room"
    assert inv.paid_total == Decimal("10500")
    assert inv.grand_total == Decimal("10500")
    assert inv.items.count() >= 1, "charge lines must be copied onto the bill"


def test_folio_charges_stay_hidden_from_the_invoice_list():
    """The whole point: internal line items must not look like sales."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )

    for ch in folio.charges.select_related("invoice").all():
        assert ch.invoice.is_held is True, (
            f"{ch.invoice.local_invoice_number} leaked into the invoice list"
        )
        assert ch.invoice.paid_total == Decimal("0"), (
            "a charge row must never carry the settlement payment"
        )


def test_stay_revenue_is_counted_exactly_once():
    """Sum what the invoice list would show; it must equal the stay's value."""
    from apps.sales.models import Invoice

    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )

    visible = Invoice.objects.filter(
        tenant_id=tenant.id, is_held=False, deleted_at__isnull=True,
    )
    assert visible.count() == 1, "exactly one invoice per stay"
    assert sum(i.grand_total for i in visible) == Decimal("10500")


def test_bill_reports_the_settlement_invoice_number():
    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )

    bill = services.consolidated_bill(folio)
    assert bill["settlement_invoice_number"] == folio.settlement_invoice.local_invoice_number
    assert bill["paid_total"] == "10500.0000"
    assert bill["balance"] == "0.0000"


def test_backfill_repairs_a_legacy_closed_folio():
    """A stay closed by the OLD code: charges un-held, payment on an anchor.

    The backfill must mint the missing invoice, move the payment onto it, and
    make the charges internal again — without destroying the original
    Payment row (its tender and proof fields are real history).
    """
    from decimal import Decimal as D

    from django.core.management import call_command

    from apps.sales.models import Invoice, Payment

    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )

    # Recreate the LEGACY end-state by hand.
    charge = folio.charges.select_related("invoice").first()
    anchor = charge.invoice
    anchor.is_held = False
    anchor.paid_total = D("10500")
    anchor.save(update_fields=["is_held", "paid_total"])
    original = Payment.objects.create(
        tenant_id=tenant.id, invoice=anchor, payment_method="card",
        amount=D("10500"), status="completed", card_last4="4242",
    )
    folio.status = "closed"
    folio.save(update_fields=["status"])

    call_command("backfill_folio_settlements", "--apply", stdout=StringIO())

    folio.refresh_from_db()
    assert folio.settlement_invoice is not None
    inv = folio.settlement_invoice
    assert not inv.local_invoice_number.startswith("FOL-")
    assert inv.paid_total == D("10500")

    # The ORIGINAL payment moved — not a copy, so the card proof survives.
    original.refresh_from_db()
    assert original.invoice_id == inv.id
    assert original.card_last4 == "4242"
    assert Payment.objects.filter(tenant_id=tenant.id).count() == 1, "must not duplicate"

    # The charge is internal again and carries no payment.
    anchor.refresh_from_db()
    assert anchor.is_held is True
    assert anchor.paid_total == D("0")

    # And the invoice list shows exactly one row for the stay.
    visible = Invoice.objects.filter(
        tenant_id=tenant.id, is_held=False, deleted_at__isnull=True,
    )
    assert visible.count() == 1
    assert visible.first().id == inv.id


def test_backfill_is_idempotent():
    from django.core.management import call_command

    tenant, branch, terminal, cashier, room, _ = _setup()
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "10500"}],
    )
    first = folio.settlement_invoice_id

    call_command("backfill_folio_settlements", "--apply", stdout=StringIO())

    folio.refresh_from_db()
    assert folio.settlement_invoice_id == first, "must skip an already-settled folio"


# --- Optional room extras (extra mattress) --------------------------------
# A mattress is an ADD-ON to a room, not a room. With no way to charge one,
# staff created fake Room records named "mattress" / "STANDARD MATTRESS" —
# neither has a linked product, so checking a guest into one fails with
# "Room mattress has no linked product." right in front of the guest.

def _mattress(tenant):
    from apps.catalog.models import Category, Product, UnitOfMeasure

    cat, _ = Category.objects.get_or_create(tenant=tenant, name="Room Extras")
    return Product.objects.create(
        tenant=tenant, category=cat, name="Extra Mattress",
        sku=f"EXTRA-MATTRESS-{uuid.uuid4().hex[:6]}",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("1000"), cost_price=Decimal("0"),
    )


def test_mattress_can_be_added_at_check_in():
    tenant, branch, terminal, cashier, room, _ = _setup()
    mattress = _mattress(tenant)

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
        extras=[{"product": str(mattress.id), "quantity": "1"}],
    )

    bill = services.consolidated_bill(folio)
    names = [
        it["name"]
        for day in bill["days"] for ch in day["charges"] for it in ch["items"]
    ]
    assert "Extra Mattress" in names, names
    # Room 10500 + mattress 1000.
    assert bill["grand_total"] == "11500.0000"


def test_two_mattresses_charge_twice():
    tenant, branch, terminal, cashier, room, _ = _setup()
    mattress = _mattress(tenant)

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
        extras=[{"product": str(mattress.id), "quantity": "2"}],
    )

    assert services.consolidated_bill(folio)["grand_total"] == "12500.0000"


def test_no_extras_means_no_extra_charge():
    """The guest who does not want one must not be billed for one."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    _mattress(tenant)

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
        extras=[],
    )

    assert services.consolidated_bill(folio)["grand_total"] == "10500.0000"
    assert folio.charges.filter(kind="misc").count() == 0


def test_mattress_can_be_added_later_to_an_open_folio():
    """A guest asks at 11pm — it must go on the same bill, not a new sale."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    mattress = _mattress(tenant)

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
    )
    services.add_extras(
        folio=folio, extras=[{"product": str(mattress.id), "quantity": "1"}],
        terminal=terminal, cashier=cashier, cash_session=None,
    )

    assert services.consolidated_bill(folio)["grand_total"] == "11500.0000"


def test_mattress_is_settled_on_the_one_stay_invoice():
    """It must land on the guest's single invoice, not a separate sale."""
    tenant, branch, terminal, cashier, room, _ = _setup()
    mattress = _mattress(tenant)

    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, guest_name="Ali", guest_cnic="111", guest_phone="0300",
        room=room, check_in=timezone.now(),
        expected_check_out=timezone.now() + dt.timedelta(days=1),
        extras=[{"product": str(mattress.id), "quantity": "1"}],
    )
    folio = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "11500"}],
    )

    inv = folio.settlement_invoice
    assert inv.grand_total == Decimal("11500")
    assert "Extra Mattress" in [i.product_name for i in inv.items.all()]


# --- Card vs cash services tax at folio checkout -------------------------
#
# TDCP's rule: a bill paid entirely by card is taxed at the reduced rate (8%),
# any cash at the standard one (16%). The folio checkout has its own payment
# picker and never applied it, so a card-paying guest was promised 8% on the
# terminal and charged 16% on the bill.
#
# Room nights are exempt: VIP 8820 + 1680 = 10500/night is the resort's
# declared tariff, not a percentage we may recompute.

def _card(amount: str) -> dict:
    """A card tender. The POS requires the slip details, so supply them."""
    return {
        "payment_method": "card_credit", "amount": amount,
        "card_last4": "4242", "card_auth_code": "123456",
    }


def _card_tenant(tenant):
    tenant.services_tax_rate_standard = Decimal("16.00")
    tenant.services_tax_rate_card = Decimal("8.00")
    tenant.save(update_fields=[
        "services_tax_rate_standard", "services_tax_rate_card",
    ])
    return tenant


def _stay_with_food(tenant, branch, terminal, cashier, room, biryani, *, qty="1"):
    """One night (VIP 8820+1680) plus one Rs 500 biryani charged to the folio."""
    check_in = timezone.make_aware(dt.datetime(2026, 6, 30, 18, 0))
    folio = services.open_stay(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, room=room,
        guest_name="Card Guest", guest_cnic="3520111111111",
        guest_phone="03001234567",
        check_in=check_in,
        expected_check_out=check_in + dt.timedelta(days=1),  # 1 night
    )
    services.add_charge(
        folio=folio, terminal=terminal, cashier=cashier, cash_session=None,
        cart_lines=[{
            "product": str(biryani.id), "quantity": qty,
            "unit_price": "500.00", "tax_rate": "16.00", "is_taxable": True,
        }],
        kind="restaurant",
    )
    return GuestFolio.objects.get(pk=folio.pk)


def test_folio_paid_by_card_taxes_food_at_the_reduced_rate():
    """THE reported bug: 8% shown on the terminal, 16% actually charged."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    bill_total = services.consolidated_bill(folio)["grand_total"]
    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[_card(str(bill_total))],
    )
    inv = settled.settlement_invoice

    # Room: 8820 + 1680 declared = 10500, untouched.
    # Food: 500 @ 8% = 40  (was 80 at 16%).
    assert inv.tax_total == Decimal("1720.0000"), (
        f"expected room 1680 + food 40, got {inv.tax_total}"
    )
    assert inv.grand_total == Decimal("11040.0000")


def test_folio_paid_by_cash_keeps_the_standard_rate():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    bill_total = services.consolidated_bill(folio)["grand_total"]
    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": str(bill_total)}],
    )
    inv = settled.settlement_invoice

    # Room 1680 + food 500 @ 16% = 80.
    assert inv.tax_total == Decimal("1760.0000")
    assert inv.grand_total == Decimal("11080.0000")


def test_folio_part_cash_part_card_uses_the_standard_rate():
    """Any cash in the tender → standard rate on the whole bill."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[
            _card("10000.00"),
            {"payment_method": "cash", "amount": "1080.00"},
        ],
    )
    assert settled.settlement_invoice.tax_total == Decimal("1760.0000")


def test_room_night_tax_is_never_re_rated_by_the_payment_method():
    """The declared tariff must survive a card payment untouched."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[_card("11040.00")],
    )
    rooms = [
        it for it in settled.settlement_invoice.items.all()
        if "Room" in (it.product_name or "")
    ]
    assert rooms, "expected a room line on the settlement invoice"
    assert sum(it.tax_amount for it in rooms) == Decimal("1680.0000"), (
        "the room's declared fixed tax must not change with the payment method"
    )


def test_settlement_totals_match_the_sum_of_its_own_lines():
    """The printed receipt reads these columns — they must reconcile exactly."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[_card("11040.00")],
    )
    inv = settled.settlement_invoice
    items = list(inv.items.all())

    assert sum(it.tax_amount for it in items) == inv.tax_total
    assert sum(it.line_total for it in items) == inv.grand_total
    assert inv.subtotal + inv.tax_total == inv.grand_total


def test_a_tenant_without_a_card_rate_is_unaffected():
    """Every non-TDCP resort must behave exactly as before."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    tenant.services_tax_rate_card = None
    tenant.save(update_fields=["services_tax_rate_card"])
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[_card("11080.00")],
    )
    # Food stays at 16% → 80, room 1680.
    assert settled.settlement_invoice.tax_total == Decimal("1760.0000")


def test_the_printed_bill_matches_the_settlement_invoice_after_a_card_checkout():
    """The receipt is printed from consolidated_bill — it must not show 16%
    while the invoice the guest pays says 8%."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier, payments=[_card("11040.00")],
    )
    bill = services.consolidated_bill(settled)
    inv = settled.settlement_invoice

    assert bill["tax_total"] == str(inv.tax_total), (
        f"receipt {bill['tax_total']} vs invoice {inv.tax_total}"
    )
    assert bill["grand_total"] == str(inv.grand_total)
    assert bill["subtotal"] == str(inv.subtotal)
    # And it is the reduced-rate figure, not the standard one.
    assert bill["tax_total"] == "1720.0000"
    assert bill["balance"] == "0.0000", "a fully-paid stay must show no balance"


def test_the_printed_bill_still_matches_on_a_cash_checkout():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[{"payment_method": "cash", "amount": "11080.00"}],
    )
    bill = services.consolidated_bill(settled)

    assert bill["tax_total"] == str(settled.settlement_invoice.tax_total)
    assert bill["tax_total"] == "1760.0000"


def test_an_open_folio_still_quotes_the_standard_rate():
    """Before checkout nothing is settled, so the running tab shows 16% —
    the guest is never promised a total we then have to raise."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    bill = services.consolidated_bill(folio)

    assert bill["settlement_invoice_number"] is None
    assert bill["tax_total"] == "1760.0000", "room 1680 + food 80 @ 16%"


def test_the_card_preview_equals_what_a_card_checkout_actually_charges():
    """The cashier's quote must be the number the server then bills."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    preview = services.consolidated_bill(folio)["card_rate_preview"]
    assert preview is not None
    assert preview["rate"] == "8.00"
    assert preview["tax_total"] == "1720.0000"
    assert preview["grand_total"] == "11040.0000"

    settled = services.checkout_stay(
        folio=folio, cashier=cashier,
        payments=[_card(preview["grand_total"])],
    )
    inv = settled.settlement_invoice
    assert preview["tax_total"] == str(inv.tax_total)
    assert preview["grand_total"] == str(inv.grand_total)


def test_no_card_preview_once_the_stay_is_settled():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)
    settled = services.checkout_stay(
        folio=folio, cashier=cashier, payments=[_card("11040.00")],
    )
    assert services.consolidated_bill(settled)["card_rate_preview"] is None


def test_no_card_preview_when_the_tenant_has_no_card_rate():
    tenant, branch, terminal, cashier, room, biryani = _setup()
    tenant.services_tax_rate_card = None
    tenant.save(update_fields=["services_tax_rate_card"])
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)
    assert services.consolidated_bill(folio)["card_rate_preview"] is None


def test_the_printed_line_items_add_up_to_the_printed_total():
    """The receipt lists per-charge amounts and then a Tax/Total block. A guest
    adding up the lines must reach the total they are asked to pay."""
    tenant, branch, terminal, cashier, room, biryani = _setup()
    _card_tenant(tenant)
    folio = _stay_with_food(tenant, branch, terminal, cashier, room, biryani)

    settled = services.checkout_stay(
        folio=folio, cashier=cashier, payments=[_card("11040.00")],
    )
    bill = services.consolidated_bill(settled)

    charge_total = sum(
        Decimal(c["total"]) for d in bill["days"] for c in d["charges"]
    )
    charge_tax = sum(
        Decimal(c["tax"]) for d in bill["days"] for c in d["charges"]
    )
    assert charge_total == Decimal(bill["grand_total"]), (
        f"lines sum to {charge_total} but the bill says {bill['grand_total']}"
    )
    assert charge_tax == Decimal(bill["tax_total"])
