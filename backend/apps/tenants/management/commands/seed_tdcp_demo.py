"""Seed the TDCP Lake Resort Kallar Kahar demo tenant (non-fiscal).

A plain resort POS — rooms + restaurant — that prints normal bills with a 16%
Punjab Sales Tax line but is NOT connected to any tax authority
(fbr_connection_type="none"), so nothing is ever submitted to FBR/PRA.

Creates: tenant (vertical=restaurant, mode=pos, non-fiscal) → owner + cashier
(PIN) → branch "Kallar Kahar" → terminal (pairing code for the .exe) → 16%
Punjab Sales Tax rate → a "Rooms" category with room-night products → the full
real restaurant menu (11 categories) → dining tables.

Idempotent (reuse by ntn / email / sku). Prints credentials + pairing code.

    python manage.py seed_tdcp_demo
    python manage.py seed_tdcp_demo --owner-password 'X'
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, HsCode, Product, TaxRate, UnitOfMeasure
from apps.restaurant.models import Table
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal

User = get_user_model()

FOOD_HS = "2106.9090"   # Miscellaneous edible preparations — safe for menu items.
ROOM_HS = "9963.0000"   # Accommodation services (best-effort; non-fiscal anyway).

# Rooms — TDCP Kallar Kahar real tariff. Tax is a FIXED AMOUNT per night (not %),
# scaled by nights × rooms. Each tuple:
#   (type, sku, nightly_base, nightly_tax, room_numbers)  →  base + tax = total/night
# room_numbers are the ACTUAL floor numbers at the resort (not sequential 1..n).
ROOM_TYPES = [
    ("VIP",    "ROOM-VIP", "8820", "1680", ["101", "102", "109", "110", "116"]),  # 10500/night
    ("Deluxe", "ROOM-DLX", "6300", "1200", ["111", "112", "113", "114", "115"]),  # 7500/night
    ("Standard", "ROOM-STD", "5040", "960", ["107", "108"]),                       # 6000/night
]

# Full restaurant menu, transcribed from the TDCP Lake Resort Kallar Kahar menu
# card. Portioned items (Half/Full, kg, persons, pieces) are SEPARATE products,
# exactly as printed.  (category, name, sku, price)
MENU = [
    # --- Beverages ---
    ("Beverages", "Soft Drink", "BEV-SOFT", "90"),
    ("Beverages", "Fresh Lime", "BEV-LIME", "130"),
    ("Beverages", "Mineral Water", "BEV-WATER", "180"),
    ("Beverages", "Lassi", "BEV-LASSI", "180"),
    ("Beverages", "Milk Glass", "BEV-MILK", "210"),
    ("Beverages", "Cold Coffee", "BEV-COLDCOF", "360"),
    ("Beverages", "Tea", "BEV-TEA", "110"),
    ("Beverages", "Gur wali Chai", "BEV-GURCHAI", "120"),
    ("Beverages", "Hot Coffee", "BEV-HOTCOF", "290"),
    ("Beverages", "Cream Coffee", "BEV-CREAMCOF", "360"),
    ("Beverages", "Green Tea", "BEV-GREENTEA", "80"),
    # --- Salad Bar ---
    ("Salad Bar", "Kachumar Salad", "SAL-KACHUMAR", "260"),
    ("Salad Bar", "Chicken Salad", "SAL-CHICKEN", "480"),
    ("Salad Bar", "Fresh Salad", "SAL-FRESH", "180"),
    ("Salad Bar", "Raita", "SAL-RAITA", "120"),
    ("Salad Bar", "Mint Raita", "SAL-MINTRAITA", "150"),
    ("Salad Bar", "Achar", "SAL-ACHAR", "120"),
    ("Salad Bar", "Russian Salad", "SAL-RUSSIAN", "480"),
    # --- Breakfast ---
    ("Breakfast", "Omelette", "BRK-OMELETTE", "200"),
    ("Breakfast", "Egg Fry", "BRK-EGGFRY", "140"),
    ("Breakfast", "Egg Boiled", "BRK-EGGBOIL", "70"),
    ("Breakfast", "Paratha", "BRK-PARATHA", "120"),
    ("Breakfast", "Toast", "BRK-TOAST", "25"),
    ("Breakfast", "French Toast (4 Piece)", "BRK-FRTOAST", "240"),
    # --- B.B.Q ---
    ("B.B.Q", "Chicken Malai Boti", "BBQ-MALAI", "1520"),
    ("B.B.Q", "Chicken Tikka Boti", "BBQ-TIKKABOTI", "1320"),
    ("B.B.Q", "Chicken Seekh Kabab", "BBQ-SEEKH", "840"),
    ("B.B.Q", "Chicken Tikka Piece", "BBQ-TIKKAPC", "600"),
    ("B.B.Q", "Kallar Kahar Special Chicken", "BBQ-KKSPECIAL", "1800"),
    ("B.B.Q", "Reshmi Kabab", "BBQ-RESHMI", "1150"),
    # --- Fish (Seasonal) ---
    ("Fish (Seasonal)", "BBQ Fish Grill 1 Kg", "FSH-BBQ-1KG", "2160"),
    ("Fish (Seasonal)", "BBQ Fish Grill 1/2 Kg", "FSH-BBQ-HALF", "1080"),
    ("Fish (Seasonal)", "Fried Fish 1 Kg", "FSH-FRIED-1KG", "2160"),
    ("Fish (Seasonal)", "Fried Fish 1/2 Kg", "FSH-FRIED-HALF", "1080"),
    # --- Choice of Snacks ---
    ("Snacks", "Club Sandwich", "SNK-CLUB", "540"),
    ("Snacks", "Chicken Chilly Sandwich", "SNK-CHILLY", "480"),
    ("Snacks", "Chicken Sandwich", "SNK-CHICKEN", "420"),
    ("Snacks", "Chicken Cutlets", "SNK-CUTLETS", "840"),
    ("Snacks", "Chicken Drum Stick (4 Pieces)", "SNK-DRUMSTICK", "1220"),
    ("Snacks", "French Fries", "SNK-FRIES", "420"),
    # --- Dairy Ice-Cream ---
    ("Dairy Ice-Cream", "Two Scoop (Mango/Strawberry/Dates/Chocolate/Oreo/Peach/Almond)", "ICE-TWOSCOOP", "360"),
    # --- Chinese Dishes (02 persons unless noted) ---
    ("Chinese Dishes", "Chicken Manchurian (2 Persons)", "CHN-MANCHURIAN", "1080"),
    ("Chinese Dishes", "Chicken Chowmein (2 Persons)", "CHN-CHOWMEIN", "1460"),
    ("Chinese Dishes", "Chicken Garlic Sauce (2 Persons)", "CHN-GARLIC", "1200"),
    ("Chinese Dishes", "Sweet & Sour Chicken (2 Persons)", "CHN-SWEETSOUR", "1200"),
    ("Chinese Dishes", "Chicken with Mix Vegetable", "CHN-MIXVEG", "1020"),
    ("Chinese Dishes", "Chicken with Almond (2 Persons)", "CHN-ALMOND", "1200"),
    ("Chinese Dishes", "Hot & Sour Chicken (2 Persons)", "CHN-HOTSOUR", "1200"),
    ("Chinese Dishes", "Chicken Chilli Dry (2 Persons)", "CHN-CHILLIDRY", "1150"),
    ("Chinese Dishes", "Chicken Pine Apple (2 Persons)", "CHN-PINEAPPLE", "1440"),
    # --- Soups ---
    ("Soups", "TDCP Special Soup (2 Persons)", "SOUP-TDCP", "1300"),
    ("Soups", "Chicken Corn Soup (2 Persons)", "SOUP-CORN", "1200"),
    ("Soups", "Hot & Sour Soup (2 Persons)", "SOUP-HOTSOUR", "1200"),
    ("Soups", "Chicken Thai Soup (2 Persons)", "SOUP-THAI", "1250"),
    ("Soups", "Chicken Vegetable Soup (4 Persons)", "SOUP-VEG", "1360"),
    ("Soups", "Chicken Yakhni (1 Cup)", "SOUP-YAKHNI", "390"),
    # --- Pakistani Dishes ---
    ("Pakistani Dishes", "Desi Murgh", "PAK-DESIMURGH", "4080"),
    ("Pakistani Dishes", "White Chicken Handi (Full)", "PAK-WHITEHANDI-F", "2800"),
    ("Pakistani Dishes", "Chicken Handi Boneless (Full)", "PAK-BLHANDI-F", "2550"),
    ("Pakistani Dishes", "Chicken Handi Boneless (Half)", "PAK-BLHANDI-H", "1140"),
    ("Pakistani Dishes", "Chicken Karahi (Full)", "PAK-CKARAHI-F", "2100"),
    ("Pakistani Dishes", "Chicken Karahi (Half)", "PAK-CKARAHI-H", "1120"),
    ("Pakistani Dishes", "Chicken Achari Handi (Full)", "PAK-ACHARIHANDI-F", "2520"),
    ("Pakistani Dishes", "Mutton Karahi (Full)", "PAK-MKARAHI-F", "4320"),
    ("Pakistani Dishes", "Mutton Karahi (Half)", "PAK-MKARAHI-H", "2280"),
    ("Pakistani Dishes", "Mutton Masala (2 Persons)", "PAK-MUTTONMASALA", "1550"),
    ("Pakistani Dishes", "Chicken Masala (2 Persons)", "PAK-CMASALA", "1150"),
    ("Pakistani Dishes", "Chicken Steam Roast (Full)", "PAK-STEAMROAST-F", "2110"),
    ("Pakistani Dishes", "Chicken Ginger (2 Persons)", "PAK-GINGER", "1290"),
    ("Pakistani Dishes", "Chicken Jalfrezi (2 Persons)", "PAK-JALFREZI", "1290"),
    ("Pakistani Dishes", "Chicken Badami Korma", "PAK-BADAMI", "1510"),
    ("Pakistani Dishes", "Chicken Steak (2 Persons)", "PAK-STEAK", "1510"),
    ("Pakistani Dishes", "Mix Vegetable (1 Plate)", "PAK-MIXVEG", "430"),
    ("Pakistani Dishes", "Daal Mash (1 Plate)", "PAK-DAALMASH", "430"),
    # --- Rice ---
    ("Rice", "TDCP Special Rice", "RICE-TDCP", "1150"),
    ("Rice", "Chicken Biryani (2 Persons)", "RICE-CBIRYANI", "1150"),
    ("Rice", "Mutton Biryani (2 Persons)", "RICE-MBIRYANI", "1300"),
    ("Rice", "Chicken Fried Rice (2 Persons)", "RICE-CFRIED", "1020"),
    ("Rice", "Vegetable Fried Rice (2 Persons)", "RICE-VFRIED", "900"),
    ("Rice", "Egg Fried Rice", "RICE-EGGFRIED", "920"),
    ("Rice", "Masala Rice (2 Persons)", "RICE-MASALA", "1050"),
    ("Rice", "Plain Rice (2 Persons)", "RICE-PLAIN", "480"),
    ("Rice", "Chicken Shashlik", "RICE-SHASHLIK", "1350"),
    # --- Dessert ---
    ("Dessert", "Fruit Trifle (4 Person)", "DST-TRIFLE", "1450"),
    ("Dessert", "Kheer (4 Person)", "DST-KHEER", "1450"),
    # --- Live Tandoor ---
    ("Live Tandoor", "Roti", "TND-ROTI", "25"),
    ("Live Tandoor", "Naan", "TND-NAAN", "80"),
    ("Live Tandoor", "Roghni Naan", "TND-ROGHNI", "120"),
]

# Category display order (Rooms first so it's the most prominent on the till).
CATEGORY_ORDER = [
    "Rooms", "Pakistani Dishes", "B.B.Q", "Rice", "Chinese Dishes", "Soups",
    "Fish (Seasonal)", "Snacks", "Breakfast", "Salad Bar", "Live Tandoor",
    "Beverages", "Dairy Ice-Cream", "Dessert",
]


class Command(BaseCommand):
    help = "Seed the TDCP Kallar Kahar non-fiscal resort demo (rooms + full restaurant menu)."

    def add_arguments(self, parser):
        parser.add_argument("--ntn", default="7700001")
        parser.add_argument("--business-name", default="TDCP Lake Resort Kallar Kahar")
        parser.add_argument("--owner-email", default="owner@tdcp-demo.pk")
        parser.add_argument("--owner-password", default="Tdcp@2026")
        parser.add_argument("--cashier-email", default="cashier@tdcp-demo.pk")
        parser.add_argument("--cashier-pin", default="135790")

    @transaction.atomic
    def handle(self, *args, **opts):
        ntn = opts["ntn"]

        # 1) Tenant — POS + restaurant vertical + NON-FISCAL (no FBR/PRA).
        tenant, created = Tenant.objects.get_or_create(
            ntn=ntn,
            defaults={
                "business_name": opts["business_name"],
                "business_type": "sole_proprietor",
                "province": "PUNJAB",
                "business_mode": "pos",
                "vertical": "restaurant",
                "fbr_connection_type": "none",
                "phone": "0300 204 1742",
                "address": "TDCP Lake Resort, Kallar Kahar, Chakwal, Punjab",
                "subscription_status": "active",
            },
        )
        if not created:
            tenant.business_name = opts["business_name"]
            tenant.business_mode = "pos"
            tenant.vertical = "restaurant"
            tenant.fbr_connection_type = "none"
            tenant.phone = "0300 204 1742"
            tenant.address = "TDCP Lake Resort, Kallar Kahar, Chakwal, Punjab"
            tenant.save()
        # Enable the `hotel` module (rooms + folios) for this rooms+restaurant
        # tenant — idempotent. Restaurant-only POS tenants don't get it.
        mods = list(tenant.modules_enabled or [])
        for m in ("hotel", "restaurant"):
            if m not in mods:
                mods.append(m)
        tenant.modules_enabled = mods
        tenant.save(update_fields=["modules_enabled", "updated_at"])

        self.stdout.write(
            f"Tenant: {tenant.business_name} ({tenant.ntn}) "
            f"[{'created' if created else 'updated'}] — non-fiscal, hotel+restaurant"
        )

        # 2) Owner + 3) Cashier (PIN for the terminal)
        owner = self._user(opts["owner_email"], "TDCP Manager", password=opts["owner_password"])
        TenantMembership.objects.get_or_create(tenant=tenant, user=owner, defaults={"role": "owner"})
        cashier = self._user(
            opts["cashier_email"], "TDCP Cashier",
            password=opts["owner_password"], pin=opts["cashier_pin"],
        )
        TenantMembership.objects.get_or_create(tenant=tenant, user=cashier, defaults={"role": "cashier"})

        # 4) Branch + Terminal (pairing code for the .exe)
        branch, _ = Branch.objects.get_or_create(
            tenant=tenant, code="KK",
            defaults={
                "name": "Kallar Kahar", "address": "TDCP Lake Resort, Kallar Kahar",
                "city": "Kallar Kahar", "province": "PUNJAB", "is_default": True,
            },
        )
        terminal, _ = Terminal.objects.get_or_create(
            tenant=tenant, branch=branch, name="Reception Counter",
            defaults={"device_fingerprint": f"seed-{ntn}-reception"},
        )
        pairing_code = terminal.issue_pairing_code()

        # 5) Tax rate — 16% Punjab Sales Tax (shown on the bill; NOT submitted).
        tax_rate, _ = TaxRate.objects.get_or_create(
            tenant=tenant, name="Punjab Sales Tax 16%",
            defaults={"rate": Decimal("16.00"), "is_default": True, "applies_to": "both"},
        )

        food_hs = HsCode.objects.filter(code=FOOD_HS).first()
        room_hs = HsCode.objects.filter(code=ROOM_HS).first() or food_hs
        uom_pcs = UnitOfMeasure.objects.filter(code="PCS").first()
        # A "NIGHT" unit so room lines read "Deluxe Room / night x 3" naturally.
        uom_night, _ = UnitOfMeasure.objects.get_or_create(
            code="NIGHT",
            defaults={"name_en": "Night", "name_ur": "رات", "is_decimal_quantity": False},
        )

        # 6) Categories (Rooms first → highest prominence on the till).
        all_cats = ["Rooms"] + list(dict.fromkeys(m[0] for m in MENU))
        categories: dict[str, Category] = {}
        for cat_name in all_cats:
            order = CATEGORY_ORDER.index(cat_name) if cat_name in CATEGORY_ORDER else 99
            cat, _ = Category.objects.get_or_create(
                tenant=tenant, slug=slugify(cat_name),
                defaults={"name": cat_name, "display_order": order},
            )
            if cat.display_order != order:
                cat.display_order = order
                cat.save(update_fields=["display_order"])
            categories[cat_name] = cat

        # 7) Rooms — one Product per room type + individual Room rows for
        #    occupancy. Room tax is a FIXED AMOUNT per night (set on the Room),
        #    applied at folio time — so the room Product itself carries no
        #    tax_rate (the folio service computes the exact line tax).
        from apps.hotel.models import Room

        n_room_products = 0
        n_rooms = 0
        # Every room number we intend to keep — used to prune stale rooms below.
        wanted_numbers: set[str] = set()
        for room_type, sku, base, tax_amt, room_numbers in ROOM_TYPES:
            product, _ = Product.objects.get_or_create(
                tenant=tenant, sku=sku,
                defaults={
                    "name": f"{room_type} Room / night",
                    "category": categories["Rooms"],
                    "uom": uom_night,
                    "tax_rate": None,            # tax applied per-night as fixed amount
                    "hs_code": room_hs,
                    "sale_price": Decimal(base),
                    "cost_price": Decimal("0.0000"),
                    "is_taxable": True,
                },
            )
            # Keep the product's price/name in sync on re-run.
            product.name = f"{room_type} Room / night"
            product.sale_price = Decimal(base)
            product.category = categories["Rooms"]
            product.uom = uom_night
            product.save(update_fields=["name", "sale_price", "category", "uom", "updated_at"])
            n_room_products += 1

            # Individual rooms keyed by their ACTUAL floor number (VIP: 101/102/
            # 109/110/116, Deluxe: 111-115, Standard: 107/108).
            for i, number in enumerate(room_numbers, start=1):
                wanted_numbers.add(number)
                room, _ = Room.objects.get_or_create(
                    tenant=tenant, branch=branch, room_number=number,
                    defaults={
                        "room_type": room_type,
                        "nightly_base": Decimal(base),
                        "nightly_tax": Decimal(tax_amt),
                        "product": product,
                        "display_order": n_room_products * 100 + i,
                        "status": "available",
                    },
                )
                # Keep type/pricing/product in sync on re-run (e.g. a room number
                # that previously existed under a different type).
                room.room_type = room_type
                room.nightly_base = Decimal(base)
                room.nightly_tax = Decimal(tax_amt)
                room.product = product
                room.display_order = n_room_products * 100 + i
                room.is_active = True
                room.save(update_fields=[
                    "room_type", "nightly_base", "nightly_tax", "product",
                    "display_order", "is_active", "updated_at",
                ])
                n_rooms += 1

        # Prune rooms that are NOT in the new list (e.g. the old sequential
        # VIP-1..5 / DLX-1..5 / STD-1..6). Only delete rooms with no folio
        # history; otherwise deactivate them so past bills stay intact.
        n_pruned = 0
        stale = Room.objects.filter(tenant=tenant, branch=branch).exclude(
            room_number__in=wanted_numbers,
        )
        for r in stale:
            if r.folios.exists() or r.folio_rooms.exists():
                if r.is_active or r.status != "maintenance":
                    r.is_active = False
                    r.status = "maintenance"
                    r.save(update_fields=["is_active", "status", "updated_at"])
                    n_pruned += 1
            else:
                r.delete()
                n_pruned += 1

        # 8) Restaurant menu items.
        n_menu = 0
        for cat_name, name, sku, price in MENU:
            Product.objects.get_or_create(
                tenant=tenant, sku=sku,
                defaults={
                    "name": name,
                    "category": categories[cat_name],
                    "uom": uom_pcs,
                    "tax_rate": tax_rate,
                    "hs_code": food_hs,
                    "sale_price": Decimal(price),
                    "cost_price": (Decimal(price) * Decimal("0.5")).quantize(Decimal("0.0001")),
                    "is_taxable": True,
                },
            )
            n_menu += 1

        # 9) Dining tables (a few zones for the restaurant).
        for i, (nm, seats, zone) in enumerate([
            ("L1", 4, "Lakeside"), ("L2", 4, "Lakeside"), ("L3", 6, "Lakeside"),
            ("H1", 4, "Main Hall"), ("H2", 4, "Main Hall"), ("H3", 2, "Main Hall"),
            ("G1", 8, "Garden"), ("G2", 8, "Garden"),
        ]):
            Table.objects.get_or_create(
                tenant=tenant, branch=branch, name=nm,
                defaults={"seats": seats, "zone": zone, "display_order": i},
            )

        # --- Summary ---
        self.stdout.write(self.style.SUCCESS("\n=== TDCP Kallar Kahar demo ready (NON-FISCAL) ==="))
        self.stdout.write(f"Business : {tenant.business_name}  (NTN {tenant.ntn})")
        self.stdout.write(f"Tax      : 16% food (PST) + fixed per-night room tax (VIP 1680 / Deluxe 1200 / Standard 960)")
        self.stdout.write(f"Rooms    : {n_rooms} ({n_room_products} types), {n_pruned} stale pruned   Menu items: {n_menu}   Tables: 8")
        self.stdout.write(f"Modules  : hotel + restaurant enabled (folios + rooms)")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Admin-web login (admin/client.invoicesolution.pk):"))
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
