"""Seed a complete demo tenant for fresh-install showcasing.

Creates: a Tenant + owner + cashier + a branch + a terminal + 10 products
+ stock + 25 invoices spread over the last 7 days.

Idempotent: rerunning with the same NTN reuses the existing tenant and
appends only what is missing.

Use:
    python manage.py seed_demo_data --ntn 7777777 --owner-email demo@example.com
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, Product, UnitOfMeasure
from apps.inventory.services.movements import record_movement
from apps.sales.services import checkout
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal


_PRODUCTS = [
    ("Surf Excel 1kg", "SURF-1KG", "450", "300"),
    ("Tapal Tea 200g", "TAPAL-200", "250", "180"),
    ("Olper Milk 1L", "OLPR-1L", "220", "170"),
    ("Mineral Water 1.5L", "MIN-1.5L", "80", "55"),
    ("Lays Salt 30g", "LAYS-30", "30", "20"),
    ("Coca-Cola 1.5L", "COKE-1.5", "180", "120"),
    ("National Salt 800g", "SALT-800", "70", "45"),
    ("Sufi Soap 100g", "SUFI-100", "90", "60"),
    ("Knorr Cubes 50g", "KNOR-50", "120", "80"),
    ("Shan Masala 50g", "SHAN-50", "150", "100"),
]


class Command(BaseCommand):
    help = "Seed a demo tenant with realistic data for showcasing or onboarding."

    def add_arguments(self, parser):
        parser.add_argument("--ntn", default="7777777")
        parser.add_argument("--business-name", default="Demo General Store")
        parser.add_argument("--owner-email", default="demo-owner@example.com")
        parser.add_argument("--cashier-email", default="demo-cashier@example.com")
        parser.add_argument("--invoice-count", type=int, default=25)

    @transaction.atomic
    def handle(self, *args, **opts):
        tenant, _ = Tenant.objects.get_or_create(
            ntn=opts["ntn"],
            defaults={
                "business_name": opts["business_name"],
                "business_type": "sole_proprietor",
                "province": "PUNJAB",
            },
        )
        self.stdout.write(f"Tenant: {tenant.business_name} (ntn={tenant.ntn})")

        User = get_user_model()
        owner, _ = User.objects.get_or_create(
            email=opts["owner_email"],
            defaults={"full_name": "Demo Owner"},
        )
        owner.set_password("DemoPass!1")
        owner.save()
        TenantMembership.objects.get_or_create(
            tenant=tenant, user=owner, defaults={"role": "owner"},
        )

        cashier, _ = User.objects.get_or_create(
            email=opts["cashier_email"],
            defaults={"full_name": "Demo Cashier"},
        )
        cashier.set_password("DemoPass!1")
        cashier.set_pin("1234")
        cashier.save()
        TenantMembership.objects.get_or_create(
            tenant=tenant, user=cashier, defaults={"role": "cashier"},
        )

        branch, _ = Branch.objects.get_or_create(
            tenant=tenant, code="MAIN",
            defaults={
                "name": "Main", "address": "Demo address", "city": "Lahore",
                "province": "PUNJAB",
            },
        )
        terminal, _ = Terminal.objects.get_or_create(
            tenant=tenant, name="Counter 1",
            defaults={"branch": branch, "device_fingerprint": f"demo-{uuid.uuid4().hex[:6]}"},
        )

        category, _ = Category.objects.get_or_create(
            tenant=tenant, slug="grocery",
            defaults={"name": "Grocery"},
        )
        uom = UnitOfMeasure.objects.get(code="PCS")

        for name, sku, sale, cost in _PRODUCTS:
            product, created = Product.objects.get_or_create(
                tenant=tenant, sku=sku,
                defaults={
                    "name": name,
                    "category": category,
                    "uom": uom,
                    "sale_price": Decimal(sale),
                    "cost_price": Decimal(cost),
                },
            )
            if created:
                record_movement(
                    tenant_id=tenant.id, product=product, branch=branch,
                    movement_type="opening_balance", quantity=Decimal("100"),
                )

        self.stdout.write(
            f"Catalog: {Product.objects.filter(tenant=tenant).count()} products."
        )

        # Sprinkle invoices across the last 7 days.
        products = list(Product.objects.filter(tenant=tenant))
        random.seed(42)
        for i in range(opts["invoice_count"]):
            line_count = random.randint(1, 4)
            picks = random.sample(products, k=min(line_count, len(products)))
            cart_lines = [
                {
                    "product": str(p.id),
                    "quantity": str(random.randint(1, 3)),
                    "unit_price": str(p.sale_price),
                    "tax_rate": "18",
                    "is_taxable": True,
                }
                for p in picks
            ]
            total = sum(
                Decimal(line["quantity"]) * Decimal(line["unit_price"]) * Decimal("1.18")
                for line in cart_lines
            )
            inv = checkout.create_invoice(
                tenant_id=tenant.id, branch=branch, terminal=terminal,
                cashier=cashier, cash_session=None, customer=None,
                cart_lines=cart_lines,
                payments=[{"payment_method": "cash", "amount": str(total)}],
                client_uuid=uuid.uuid4(),
            )
            # Backdate up to 7 days, mark as valid for the reports.
            offset_days = random.randint(0, 6)
            from apps.sales.models import Invoice
            Invoice.objects.filter(pk=inv.pk).update(
                invoice_date=timezone.localdate() - timezone.timedelta(days=offset_days),
                status="valid",
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done. Sign in as {owner.email} / DemoPass!1"
        ))
