"""Seed a ready-to-sell retail catalog for a POS tenant.

Pre-loads ~50 of the products a typical Pakistani kiryana / general store sells
(milk, tea, biscuits, soft drinks, chocolates, ketchup, soap, shampoo, cooking
oil, cigarettes, etc.) so a POS+DI tenant can start ringing sales on day one
without hand-entering a catalog.

Design decisions (see the chat that produced this):
  - Real PRAL HS codes only. Every product maps to a code that exists in the
    synced /pdi/v1/itemdesccode catalog, so FBR won't reject the line for a
    bad HS code. Run `sync_pral_reference` first so the codes exist locally.
  - NO barcodes seeded. Real EAN-13 barcodes are unique per manufacturer SKU
    and can't be invented; the tenant scans each physical product once to bind
    its real barcode (scan-to-assign on the terminal / catalog screen).
  - POS tenants only. Refuses to run for a digital_invoicing-only tenant
    (those users don't sell physical stock) — pass --force to override.
  - Idempotent: get_or_create on (tenant, sku); re-running adds only what's
    missing and never duplicates.
  - Opening stock: a small opening_balance movement per product so the items
    are immediately sellable + show on inventory.

Usage:
    python manage.py seed_retail_catalog --ntn 7886736-0
    python manage.py seed_retail_catalog --tenant-id <uuid> [--force] [--no-stock]
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category, HsCode, Product, TaxRate, UnitOfMeasure
from apps.inventory.services.movements import record_movement
from apps.tenants.models import Branch, Tenant

# Each row: (category, name, sku, hs_code, sale_price, cost_price, uom,
#            is_third_schedule, retail_price_or_None)
# HS codes verified against the real PRAL catalog (8-digit codes).
# Prices are typical 2026 PKR retail; the tenant edits to their own.
_CATALOG: list[tuple] = [
    # --- Dairy ---
    ("Dairy", "Olper's Milk 1L (UHT)", "MILK-OLP-1L", "0401.2000", "290", "250", "LTR", False, None),
    ("Dairy", "Nestlé MilkPak 1L", "MILK-NES-1L", "0401.2000", "290", "250", "LTR", False, None),
    ("Dairy", "Nurpur Butter 200g", "BTR-NUR-200", "0405.1000", "480", "400", "PCS", False, None),
    ("Dairy", "Olper's Cream 200ml", "CRM-OLP-200", "0401.5000", "260", "210", "PCS", False, None),

    # --- Tea & Beverages ---
    ("Beverages", "Tapal Danedar 190g", "TEA-TAP-190", "0902.4090", "560", "470", "PCS", False, None),
    ("Beverages", "Lipton Yellow Label 190g", "TEA-LIP-190", "0902.4090", "590", "490", "PCS", False, None),
    ("Beverages", "Nestlé Everyday 375g", "WTNR-EVD-375", "0402.9900", "650", "540", "PCS", False, None),
    ("Beverages", "Coca-Cola 1.5L", "SD-COKE-1.5", "2202.1010", "180", "140", "PCS", False, None),
    ("Beverages", "Pepsi 1.5L", "SD-PEP-1.5", "2202.1010", "180", "140", "PCS", False, None),
    ("Beverages", "Sprite 1.5L", "SD-SPR-1.5", "2202.1010", "180", "140", "PCS", False, None),
    ("Beverages", "Nestlé Pure Life Water 1.5L", "WTR-NPL-1.5", "2201.1010", "90", "65", "PCS", False, None),
    ("Beverages", "Nestlé Fruita Vitals Juice 1L", "JCE-NFV-1L", "2009.8900", "340", "280", "PCS", False, None),
    ("Beverages", "Tang Orange 750g", "DRK-TANG-750", "2106.9090", "650", "540", "PCS", False, None),

    # --- Snacks & Confectionery ---
    ("Snacks", "Lay's Masala 60g", "CHP-LAY-60", "2005.2000", "120", "90", "PCS", False, None),
    ("Snacks", "Kurkure Chutney 70g", "CHP-KUR-70", "1905.9000", "60", "45", "PCS", False, None),
    ("Snacks", "Peek Freans Sooper 6-pack", "BIS-SOOP-6", "1905.3100", "120", "95", "PCS", False, None),
    ("Snacks", "Gala Biscuits 6-pack", "BIS-GALA-6", "1905.3100", "120", "95", "PCS", False, None),
    ("Snacks", "Dairy Milk Chocolate 38g", "CHO-DM-38", "1806.2010", "200", "160", "PCS", False, None),
    ("Snacks", "KitKat 4-finger", "CHO-KK-41", "1806.3200", "180", "145", "PCS", False, None),
    ("Snacks", "Cadbury Perk", "CHO-PERK", "1806.2090", "60", "45", "PCS", False, None),
    ("Snacks", "Candyland Toffee (each)", "CDY-CL-1", "1704.9090", "5", "3", "PCS", False, None),

    # --- Cooking / Pantry ---
    ("Pantry", "Dalda Cooking Oil 1L", "OIL-DAL-1L", "1511.9020", "560", "490", "LTR", False, None),
    ("Pantry", "Sufi Cooking Oil 1L", "OIL-SUF-1L", "1511.9020", "550", "480", "LTR", False, None),
    ("Pantry", "National Salt 800g", "SLT-NAT-800", "2501.0010", "60", "40", "PCS", False, None),
    ("Pantry", "Sugar (loose, per kg)", "SUG-LOOSE-KG", "1701.9920", "150", "130", "KG", False, None),
    ("Pantry", "Basmati Rice (per kg)", "RICE-BAS-KG", "1006.3090", "350", "290", "KG", False, None),
    ("Pantry", "Shan Biryani Masala 50g", "MAS-SHAN-BIR", "0910.9990", "180", "140", "PCS", False, None),
    ("Pantry", "National Chaat Masala 100g", "MAS-NAT-CHT", "0910.9990", "260", "210", "PCS", False, None),
    ("Pantry", "Shan Ketchup 800g", "KCH-NAT-800", "2103.2000", "480", "400", "PCS", False, None),
    ("Pantry", "Knorr Chicken Cubes 20g", "CUB-KNR-20", "2104.1000", "120", "95", "PCS", False, None),
    ("Pantry", "Maggi Noodles 70g", "NOO-MAGI-70", "1902.3000", "60", "45", "PCS", False, None),
    ("Pantry", "Nestlé Honey 250g", "HNY-NES-250", "0409.0000", "650", "540", "PCS", False, None),

    # --- Personal care ---
    ("Personal Care", "Lifebuoy Soap 100g", "SOAP-LB-100", "3401.1100", "120", "90", "PCS", False, None),
    ("Personal Care", "Lux Soap 100g", "SOAP-LUX-100", "3401.1100", "130", "100", "PCS", False, None),
    ("Personal Care", "Head & Shoulders Shampoo 185ml", "SHM-HS-185", "3305.1000", "550", "460", "PCS", False, None),
    ("Personal Care", "Sunsilk Shampoo Sachet", "SHM-SS-SAC", "3305.1000", "20", "14", "PCS", False, None),
    ("Personal Care", "Colgate Toothpaste 100g", "TP-COL-100", "3306.1010", "260", "210", "PCS", False, None),
    ("Personal Care", "Close-Up Toothpaste 100g", "TP-CU-100", "3306.1010", "240", "195", "PCS", False, None),
    ("Personal Care", "Axe Body Spray 150ml", "BSP-AXE-150", "3307.2000", "950", "780", "PCS", False, None),
    ("Personal Care", "Bonia Body Spray 120ml", "BSP-BON-120", "3307.2000", "450", "360", "PCS", False, None),
    ("Personal Care", "Junaid Jamshed Perfume 50ml", "PRF-JJ-50", "3303.0010", "2500", "1900", "PCS", False, None),
    ("Personal Care", "Pampers Diapers (each)", "DIP-PAM-1", "9619.0010", "45", "35", "PCS", False, None),
    ("Personal Care", "Always Pads 8-pack", "PAD-ALW-8", "9619.0090", "320", "260", "PCS", False, None),

    # --- Home care ---
    ("Home Care", "Surf Excel 1kg", "DET-SURF-1KG", "3402.5000", "650", "540", "PCS", False, None),
    ("Home Care", "Ariel Washing Powder 1kg", "DET-ARI-1KG", "3402.5000", "680", "560", "PCS", False, None),
    ("Home Care", "Vim Dishwash Bar", "DSH-VIM-BAR", "3401.2000", "90", "65", "PCS", False, None),
    ("Home Care", "Harpic 500ml", "CLN-HRP-500", "3402.9000", "350", "280", "PCS", False, None),
    ("Home Care", "Match Box (each)", "MTC-BOX-1", "3605.0000", "10", "6", "PCS", False, None),

    # --- Tobacco (3rd Schedule — retail price printed; taxed on MRP) ---
    ("Tobacco", "Gold Leaf Cigarettes (pack)", "CIG-GL-20", "2402.2000", "520", "470", "PCS", True, "520"),
    ("Tobacco", "Capstan Cigarettes (pack)", "CIG-CAP-20", "2402.2000", "320", "290", "PCS", True, "320"),
    ("Tobacco", "Morven Gold (pack)", "CIG-MRV-20", "2402.2000", "120", "105", "PCS", True, "120"),
]


class Command(BaseCommand):
    help = "Seed a ready-to-sell retail catalog (real PRAL HS codes) for a POS tenant."

    def add_arguments(self, parser):
        parser.add_argument("--ntn", help="Tenant NTN.")
        parser.add_argument("--tenant-id", help="Tenant UUID (alternative to --ntn).")
        parser.add_argument(
            "--force", action="store_true",
            help="Seed even for a digital_invoicing-only tenant.",
        )
        parser.add_argument(
            "--no-stock", action="store_true",
            help="Skip the opening-balance stock movement.",
        )

    def handle(self, *args, **opts):
        tenant = self._resolve_tenant(opts)
        if tenant.business_mode == "digital_invoicing" and not opts["force"]:
            raise CommandError(
                f"{tenant.business_name} is digital_invoicing-only (no physical "
                f"stock). Pass --force to seed anyway.",
            )

        # Tax + UoM + categories.
        tax_rate, _ = TaxRate.objects.get_or_create(
            tenant=tenant, name="GST 18%",
            defaults={"rate": Decimal("18.00"), "is_default": True, "applies_to": "all"},
        )
        uom_cache = {u.code: u for u in UnitOfMeasure.objects.all()}
        missing_uoms = {row[6] for row in _CATALOG} - set(uom_cache)
        if missing_uoms:
            raise CommandError(f"Missing UoMs (run unit seed): {sorted(missing_uoms)}")

        cat_cache: dict[str, Category] = {}

        # Resolve HS codes up-front; fail loudly if any is missing (so we never
        # silently seed a product FBR will reject).
        wanted_codes = {row[3] for row in _CATALOG}
        have = dict(HsCode.objects.filter(code__in=wanted_codes).values_list("code", "code"))
        missing_codes = sorted(wanted_codes - set(have))
        if missing_codes:
            raise CommandError(
                "These HS codes are not in the local catalog — run "
                "`sync_pral_reference` first:\n  " + "\n  ".join(missing_codes),
            )

        branch = (
            Branch.objects.filter(tenant=tenant, deleted_at__isnull=True)
            .order_by("-is_default", "name").first()
        )
        if not branch and not opts["no_stock"]:
            self.stdout.write(self.style.WARNING(
                "No branch found — seeding products without opening stock.",
            ))

        created = updated = stocked = 0
        with transaction.atomic():
            for (cat_name, name, sku, hs, sale, cost, uom_code,
                 is_3rd, retail) in _CATALOG:
                category = cat_cache.get(cat_name)
                if category is None:
                    category, _ = Category.objects.get_or_create(
                        tenant=tenant, slug=cat_name.lower().replace(" ", "-"),
                        defaults={"name": cat_name},
                    )
                    cat_cache[cat_name] = category

                product, was_created = Product.objects.get_or_create(
                    tenant=tenant, sku=sku,
                    defaults={
                        "name": name,
                        "category": category,
                        "uom": uom_cache[uom_code],
                        "tax_rate": tax_rate,
                        "hs_code_id": hs,
                        "is_taxable": True,
                        "sale_price": Decimal(sale),
                        "cost_price": Decimal(cost),
                        "retail_price": Decimal(retail) if retail else None,
                        "is_third_schedule": is_3rd,
                    },
                )
                if was_created:
                    created += 1
                    if branch and not opts["no_stock"]:
                        record_movement(
                            tenant_id=tenant.id, product=product, branch=branch,
                            movement_type="opening_balance", quantity=Decimal("50"),
                        )
                        stocked += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Retail catalog for {tenant.business_name}: "
            f"{created} created, {updated} already existed, "
            f"{stocked} given opening stock. "
            f"({len(_CATALOG)} products across {len(cat_cache)} categories.) "
            f"Barcodes are intentionally empty — scan-to-assign on the terminal.",
        ))

    def _resolve_tenant(self, opts) -> Tenant:
        if opts.get("tenant_id"):
            try:
                return Tenant.objects.get(pk=opts["tenant_id"])
            except Tenant.DoesNotExist:
                raise CommandError("No tenant with that id.")
        if opts.get("ntn"):
            try:
                return Tenant.objects.get(ntn=opts["ntn"])
            except Tenant.DoesNotExist:
                raise CommandError("No tenant with that NTN.")
        raise CommandError("Pass --ntn or --tenant-id.")
