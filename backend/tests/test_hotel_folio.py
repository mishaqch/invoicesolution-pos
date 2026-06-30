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
