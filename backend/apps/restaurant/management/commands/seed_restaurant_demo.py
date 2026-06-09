"""Seed a complete Restaurant / F&B demo tenant.

Creates everything a restaurant needs to demo end to end:
  tenant (vertical=restaurant, mode=pos) → owner + cashier(PIN) → branch →
  terminal (with a pairing code for the POS .exe) → tax rate → menu categories →
  a burger/pizza menu → modifier groups (size + add-ons) attached to items →
  dining tables.

Idempotent: re-running updates/reuses rows by natural key (ntn / email / sku),
so it's safe to run twice. Prints the login credentials + pairing code at the end.

    python manage.py seed_restaurant_demo
    python manage.py seed_restaurant_demo --ntn 8888001 --owner-password 'X'
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, HsCode, Product, TaxRate, UnitOfMeasure
from apps.restaurant.models import (
    MenuItemModifierGroup,
    Modifier,
    ModifierGroup,
    Table,
)
from apps.tenants.models import Branch, TenantMembership, Terminal
from apps.tenants.models import Tenant

User = get_user_model()

FOOD_HS = "2106.9090"  # Miscellaneous edible preparations — safe for menu items.

# (category, name, sku, price)
MENU = [
    ("Burgers", "Zinger Burger", "ZINGER", "550"),
    ("Burgers", "Beef Cheese Burger", "BEEF-CB", "650"),
    ("Burgers", "Crispy Chicken Burger", "CRISPY", "500"),
    ("Pizzas", "Chicken Tikka Pizza", "PIZ-TIKKA", "1200"),
    ("Pizzas", "Pepperoni Pizza", "PIZ-PEP", "1400"),
    ("Pizzas", "Fajita Pizza", "PIZ-FAJ", "1300"),
    ("Sides", "Loaded Fries", "FRIES-LOAD", "350"),
    ("Sides", "Garlic Bread", "GBREAD", "300"),
    ("Sides", "Chicken Wings (6 pcs)", "WINGS-6", "550"),
    ("Drinks", "Soft Drink Can", "DRINK-CAN", "120"),
    ("Drinks", "Fresh Lime", "LIME", "180"),
    ("Drinks", "Mineral Water", "WATER", "80"),
]

# Which products get which modifier groups.
SIZE_ITEMS = {"PIZ-TIKKA", "PIZ-PEP", "PIZ-FAJ", "DRINK-CAN", "LIME"}
ADDON_ITEMS = {"ZINGER", "BEEF-CB", "CRISPY", "PIZ-TIKKA", "PIZ-PEP", "PIZ-FAJ"}


class Command(BaseCommand):
    help = "Seed a full restaurant demo tenant (owner, cashier, terminal, menu, modifiers, tables)."

    def add_arguments(self, parser):
        parser.add_argument("--ntn", default="8800001")
        parser.add_argument("--business-name", default="Demo Pizza & Burger")
        parser.add_argument("--owner-email", default="owner@demo-restaurant.pk")
        parser.add_argument("--owner-password", default="Restaurant@2026")
        parser.add_argument("--cashier-email", default="cashier@demo-restaurant.pk")
        parser.add_argument("--cashier-pin", default="246810")

    @transaction.atomic
    def handle(self, *args, **opts):
        ntn = opts["ntn"]

        # 1) Tenant — POS mode + restaurant vertical. TenantSettings auto-seeds.
        tenant, created = Tenant.objects.get_or_create(
            ntn=ntn,
            defaults={
                "business_name": opts["business_name"],
                "business_type": "sole_proprietor",
                "province": "PUNJAB",
                "business_mode": "pos",
                "vertical": "restaurant",
                "subscription_status": "active",
            },
        )
        if not created:
            tenant.business_name = opts["business_name"]
            tenant.business_mode = "pos"
            tenant.vertical = "restaurant"
            tenant.save(update_fields=["business_name", "business_mode", "vertical", "updated_at"])
        self.stdout.write(f"Tenant: {tenant.business_name} ({tenant.ntn}) [{'created' if created else 'updated'}]")

        # 2) Owner (email + password login → admin-web)
        owner = self._user(opts["owner_email"], "Demo Owner", password=opts["owner_password"])
        TenantMembership.objects.get_or_create(tenant=tenant, user=owner, defaults={"role": "owner"})

        # 3) Cashier (email+password AND a 6-digit PIN for the terminal)
        cashier = self._user(
            opts["cashier_email"], "Demo Cashier",
            password=opts["owner_password"], pin=opts["cashier_pin"],
        )
        TenantMembership.objects.get_or_create(tenant=tenant, user=cashier, defaults={"role": "cashier"})

        # 4) Branch + Terminal (issue a pairing code for the .exe)
        branch, _ = Branch.objects.get_or_create(
            tenant=tenant, code="MAIN",
            defaults={
                "name": "Main Branch", "address": "Liberty Market, Gulberg",
                "city": "Lahore", "province": "PUNJAB", "is_default": True,
            },
        )
        terminal, _ = Terminal.objects.get_or_create(
            tenant=tenant, branch=branch, name="Counter 1",
            defaults={"device_fingerprint": f"seed-{ntn}-counter1"},
        )
        pairing_code = terminal.issue_pairing_code()

        # 5) Tax rate (GST 18%, default) + categories
        tax_rate, _ = TaxRate.objects.get_or_create(
            tenant=tenant, name="GST 18%",
            defaults={"rate": Decimal("18.00"), "is_default": True, "applies_to": "goods"},
        )
        hs = HsCode.objects.filter(code=FOOD_HS).first()
        uom = UnitOfMeasure.objects.get(code="PCS")
        categories: dict[str, Category] = {}
        for cat_name in dict.fromkeys(m[0] for m in MENU):
            categories[cat_name], _ = Category.objects.get_or_create(
                tenant=tenant, slug=slugify(cat_name),
                defaults={"name": cat_name},
            )

        # 6) Menu items
        products: dict[str, Product] = {}
        for cat_name, name, sku, price in MENU:
            product, _ = Product.objects.get_or_create(
                tenant=tenant, sku=sku,
                defaults={
                    "name": name,
                    "category": categories[cat_name],
                    "uom": uom,
                    "tax_rate": tax_rate,
                    "hs_code": hs,
                    "sale_price": Decimal(price),
                    "cost_price": (Decimal(price) * Decimal("0.5")).quantize(Decimal("0.0001")),
                    "is_taxable": True,
                },
            )
            products[sku] = product

        # 7) Modifier groups + options
        size_group, sg_new = ModifierGroup.objects.get_or_create(
            tenant=tenant, name="Size",
            defaults={"min_select": 1, "max_select": 1, "display_order": 0},
        )
        if sg_new:
            Modifier.objects.create(group=size_group, name="Regular", price_delta=Decimal("0"), display_order=0)
            Modifier.objects.create(group=size_group, name="Large", price_delta=Decimal("250"), display_order=1)

        addon_group, ag_new = ModifierGroup.objects.get_or_create(
            tenant=tenant, name="Add-ons",
            defaults={"min_select": 0, "max_select": 4, "display_order": 1},
        )
        if ag_new:
            for i, (nm, dp) in enumerate([
                ("Extra Cheese", "80"), ("Extra Patty", "150"),
                ("Jalapeños", "50"), ("Garlic Mayo", "40"),
            ]):
                Modifier.objects.create(group=addon_group, name=nm, price_delta=Decimal(dp), display_order=i)

        # 8) Attach groups to the right items
        for sku, product in products.items():
            if sku in SIZE_ITEMS:
                MenuItemModifierGroup.objects.get_or_create(product=product, group=size_group, defaults={"display_order": 0})
            if sku in ADDON_ITEMS:
                MenuItemModifierGroup.objects.get_or_create(product=product, group=addon_group, defaults={"display_order": 1})

        # 9) Dining tables
        for i, (nm, seats, zone) in enumerate([
            ("T1", 4, "Ground Floor"), ("T2", 4, "Ground Floor"),
            ("T3", 2, "Ground Floor"), ("T4", 6, "Ground Floor"),
            ("R1", 4, "Rooftop"), ("R2", 4, "Rooftop"),
        ]):
            Table.objects.get_or_create(
                tenant=tenant, branch=branch, name=nm,
                defaults={"seats": seats, "zone": zone, "display_order": i},
            )

        # --- Summary ---
        self.stdout.write(self.style.SUCCESS("\n=== Restaurant demo ready ==="))
        self.stdout.write(f"Business     : {tenant.business_name}  (NTN {tenant.ntn})")
        self.stdout.write(f"Vertical/Mode: restaurant / pos")
        self.stdout.write(f"Menu items   : {len(products)}   Tables: 6   Modifier groups: 2")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Admin-web login (admin.invoicesolution.pk):"))
        self.stdout.write(f"  Owner email   : {owner.email}")
        self.stdout.write(f"  Owner password: {opts['owner_password']}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("POS terminal (invoiceSolution.exe):"))
        self.stdout.write(f"  Pairing code  : {pairing_code}")
        self.stdout.write(f"  Cashier email : {cashier.email}")
        self.stdout.write(f"  Cashier PIN   : {opts['cashier_pin']}")
        self.stdout.write(f"  (cashier password for first sign-in: {opts['owner_password']})")

    def _user(self, email, full_name, *, password, pin=None):
        user, _ = User.objects.get_or_create(email=email, defaults={"full_name": full_name})
        user.full_name = full_name
        user.set_password(password)
        if pin:
            user.set_pin(pin)
        user.save()
        return user
