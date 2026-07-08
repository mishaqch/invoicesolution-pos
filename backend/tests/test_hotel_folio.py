"""Hotel guest-folio flow — open a stay, add charges, checkout, consolidated bill.

Covers the multi-day resort tab: room nights auto-charged with the FIXED
per-night tax amount, restaurant charges appended, room occupancy flips, and the
consolidated bill sums every charge.
"""

from __future__ import annotations

import datetime as dt
import uuid
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
