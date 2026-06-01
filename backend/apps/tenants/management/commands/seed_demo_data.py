"""Seed a complete demo tenant for fresh-install showcasing.

Creates / tops up a tenant with:
  - Owner + cashier user (skipped when reusing an existing tenant)
  - 1 branch + 1 terminal
  - 1 product category
  - 1 default tax rate (18% Pakistan GST — required by FBR submit path)
  - 10 grocery products with an HS code attached
  - Opening stock for each product
  - 2 example customers (1 registered with NTN, 1 walk-in)
  - 1 sandbox FbrToken (placeholder ciphertext so the FBR setup screen
    shows a row; submission will still fail without a real PRAL token)
  - Optionally, N invoices spread over the last 7 days

Idempotent: rerunning with the same NTN reuses the existing tenant and
appends only what is missing. Pass `--reuse-tenant-ntn <existing>` to
target a tenant you already own (e.g. the React-admin tenant you log
into) without touching its business_name or the owner password.

Use:
    # fresh demo tenant
    python manage.py seed_demo_data --ntn 7777777 --owner-email demo@example.com

    # top up an existing tenant (e.g. Chaudhary General Store)
    python manage.py seed_demo_data \\
        --reuse-tenant-ntn 0988775656773 --invoice-count 0
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, HsCode, Product, TaxRate, UnitOfMeasure
from apps.customers.models import Customer
from apps.fbr.models import FbrToken
from apps.inventory.services.movements import record_movement
from apps.returns.services.process import process_return
from apps.sales.services import checkout
from apps.sales.services.holds import hold as hold_invoice
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
        parser.add_argument(
            "--held-count", type=int, default=3,
            help=(
                "How many HELD invoices to seed. Held invoices have no "
                "payment + is_held=True; show under Invoices → Held."
            ),
        )
        parser.add_argument(
            "--return-count", type=int, default=2,
            help=(
                "How many demo Returns to seed. Returns are processed "
                "against the most recently seeded VALID invoices (one "
                "line returned per invoice). Capped at the number of "
                "available eligible invoices."
            ),
        )
        parser.add_argument(
            "--reuse-tenant-ntn",
            default=None,
            help=(
                "If supplied, top up an EXISTING tenant with this NTN. "
                "Skips user creation + password reset on the owner. "
                "Use when you already log into the React admin and just "
                "want demo catalog + customers + FBR plumbing added."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        reuse_ntn = opts.get("reuse_tenant_ntn")
        if reuse_ntn:
            # Top-up path: target a tenant the user already owns. Don't
            # touch business_name or any setup the operator already did.
            tenant = Tenant.objects.get(ntn=reuse_ntn)
            self.stdout.write(
                f"Reusing tenant: {tenant.business_name} (ntn={tenant.ntn})",
            )
        else:
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
        if reuse_ntn:
            # Find the existing owner so checkout.create_invoice has a
            # cashier user. We don't want to clobber the owner's
            # password or invent extra accounts.
            owner_membership = (
                TenantMembership.objects.filter(
                    tenant=tenant, role="owner", is_active=True,
                )
                .select_related("user").first()
            )
            if owner_membership is None:
                raise SystemExit(
                    f"Tenant {tenant.business_name} has no active owner; "
                    "cannot seed invoices without one.",
                )
            owner = owner_membership.user
            cashier = owner  # invoices use owner as cashier in top-up mode
        else:
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
                "is_default": True,
            },
        )
        terminal, _ = Terminal.objects.get_or_create(
            tenant=tenant, name="Counter 1",
            defaults={
                "branch": branch,
                # device_fingerprint is globally unique; mix in tenant
                # NTN so reruns across multiple tenants don't collide.
                "device_fingerprint": f"seed-{tenant.ntn}-{uuid.uuid4().hex[:6]}",
            },
        )

        # Default 18% GST — required for FBR submission. is_default=True
        # so products that don't explicitly set tax_rate still get one.
        tax_rate, _ = TaxRate.objects.get_or_create(
            tenant=tenant, name="GST 18%",
            defaults={"rate": Decimal("18.00"), "is_default": True,
                      "applies_to": "all"},
        )

        category, _ = Category.objects.get_or_create(
            tenant=tenant, slug="grocery",
            defaults={"name": "Grocery"},
        )
        uom = UnitOfMeasure.objects.get(code="PCS")
        # Pick a generic grocery-ish HS code so products are FBR-ready.
        # Falls back to the first available code if 1905.0000 isn't seeded.
        hs_code = (
            HsCode.objects.filter(code__startswith="1905").first()
            or HsCode.objects.first()
        )

        for name, sku, sale, cost in _PRODUCTS:
            product, created = Product.objects.get_or_create(
                tenant=tenant, sku=sku,
                defaults={
                    "name": name,
                    "category": category,
                    "uom": uom,
                    "tax_rate": tax_rate,
                    "hs_code": hs_code,
                    "is_taxable": True,
                    "sale_price": Decimal(sale),
                    "cost_price": Decimal(cost),
                },
            )
            if created:
                record_movement(
                    tenant_id=tenant.id, product=product, branch=branch,
                    movement_type="opening_balance", quantity=Decimal("100"),
                )
            else:
                # Top-up of an existing product: attach hs_code + tax_rate
                # if they were missing, so the FBR submit path is happy
                # without forcing a manual edit.
                dirty = False
                if not product.hs_code_id and hs_code is not None:
                    product.hs_code = hs_code; dirty = True
                if not product.tax_rate_id:
                    product.tax_rate = tax_rate; dirty = True
                if not product.is_taxable:
                    product.is_taxable = True; dirty = True
                if dirty:
                    product.save(update_fields=["hs_code", "tax_rate",
                                                "is_taxable"])

        self.stdout.write(
            f"Catalog: {Product.objects.filter(tenant=tenant, deleted_at__isnull=True).count()} "
            f"products.",
        )

        # Two example customers: one registered (has NTN — FBR treats as
        # B2B) and one walk-in (no NTN — FBR treats as B2C unregistered
        # and the builder substitutes the 13-zero CNIC sentinel).
        Customer.objects.get_or_create(
            tenant=tenant, customer_code="C001",
            defaults={
                "name": "Sialkot Hardware (Pvt) Ltd",
                "ntn": "1234567",
                "registration_type": "registered",
                "phone": "+92-300-1234567",
                "address": "Iqbal Town, Sialkot",
                "province": "PUNJAB",
            },
        )
        Customer.objects.get_or_create(
            tenant=tenant, customer_code="C002",
            defaults={
                "name": "Walk-in customer",
                "registration_type": "unregistered",
            },
        )

        # Sandbox FbrToken pointed at the LOCAL MOCK PRAL gateway.
        #
        # The mock lives at /__mock_pral/di_data/v1/di/* (see
        # apps/fbr/mock_pral.py) and behaves like PRAL — validates
        # payload shape, returns a synthetic FBR invoice number on
        # success. The FBR client appends "/postinvoicedata_sb" itself
        # for sandbox, so the endpoint base must be the gateway root.
        #
        # Once a real PRAL sandbox bearer is available, change this
        # endpoint to "https://gw.fbr.gov.pk" in the admin and
        # nothing else needs to change.
        mock_endpoint = "http://localhost:8000/__mock_pral"
        existing = FbrToken.objects.filter(
            tenant=tenant, environment="sandbox",
        ).first()
        if existing is None:
            tok = FbrToken(
                tenant=tenant,
                environment="sandbox",
                api_endpoint=mock_endpoint,
                is_active=True,
            )
            tok.token = "DEV-MOCK-TOKEN"
            tok.save()
        else:
            # Top-up: if the existing row still points at the placeholder
            # PRAL URL with the placeholder token, re-aim it at the mock
            # so the operator can actually exercise the flow in dev.
            if "REPLACE-WITH-REAL" in existing.token:
                existing.api_endpoint = mock_endpoint
                existing.token = "DEV-MOCK-TOKEN"
                existing.save()

        # Sprinkle invoices across the last 7 days.
        products = list(
            Product.objects.filter(tenant=tenant, deleted_at__isnull=True),
        )
        if not products:
            raise SystemExit(
                "No products on tenant — cannot seed invoices/held/returns. "
                "Re-run without the --reuse-tenant-ntn skip to add catalog.",
            )
        random.seed(42)
        from apps.fbr.qr import build_qr_payload
        from apps.sales.models import Invoice, SaleItem

        def _build_cart_lines() -> tuple[list[dict], Decimal]:
            """Return (cart_lines, expected_total_incl_tax) for a random pick.
            Tax rate is hard-coded 18% to match the seeded GST 18% tax rate;
            keep in sync with that row's `rate` if it changes."""
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
                Decimal(line["quantity"]) * Decimal(line["unit_price"])
                * Decimal("1.18")
                for line in cart_lines
            )
            return cart_lines, total

        seeded_valid_invoice_ids: list = []

        # ----- 1) Completed invoices (paid, marked valid) -----------------
        # The first `return_target` invoices are backdated AND have
        # edit_deadline_at set in the past, which flips the returns
        # routing at step 3 to "credit_note" (a separate invoice with
        # invoice_type='credit_note') instead of "amend" (which would
        # consume the tenant's 10% monthly cancel-budget, blocking the
        # seed when the budget hasn't accrued yet on a fresh tenant).
        # Remaining invoices are scattered across the last 7 days for
        # ambient list density.
        return_target = min(opts["return_count"], opts["invoice_count"])
        now = timezone.now()
        for i in range(opts["invoice_count"]):
            cart_lines, total = _build_cart_lines()
            inv = checkout.create_invoice(
                tenant_id=tenant.id, branch=branch, terminal=terminal,
                cashier=cashier, cash_session=None, customer=None,
                cart_lines=cart_lines,
                payments=[{"payment_method": "cash", "amount": str(total)}],
                client_uuid=uuid.uuid4(),
            )
            offset_days = 5 if i < return_target else random.randint(0, 6)
            validated_at = now - timezone.timedelta(days=offset_days)

            # Fake the post-FBR-validation state so the React invoice
            # detail page has a QR to render without needing a Celery
            # worker + real PRAL token. PRAL invoice numbers are 18
            # digits; format here mimics the seller-NTN-prefixed shape
            # PRAL returns in sandbox responses (close enough for demo).
            fake_fbr_number = f"7{tenant.ntn.rjust(13, '0')[:13]}{i:04d}"
            qr_payload = build_qr_payload(
                fbr_invoice_number=fake_fbr_number,
                validated_at=validated_at,
                amount=inv.grand_total,
                seller_ntn=tenant.ntn,
            )
            # edit_deadline_at: the production FBR task sets this to
            # MIN(submitted_at + 72h, end-of-month) when PRAL accepts
            # the invoice. The seed must mirror that, otherwise valid
            # invoices in dev are effectively cancellable forever
            # (the 72h check in rules.py short-circuits when the field
            # is None, silently allowing actions the real system would
            # reject).
            #
            # Return-target invoices are intentionally pushed PAST the
            # deadline so the returns flow takes the credit_note route
            # (no cancel-budget consumption). The rest get a fresh
            # in-window deadline so the React Cancel button is testable
            # against the live rule.
            if i < return_target:
                deadline = now - timezone.timedelta(hours=1)
            else:
                deadline = validated_at + timezone.timedelta(hours=72)
            update = {
                "invoice_date": timezone.localdate()
                - timezone.timedelta(days=offset_days),
                "created_at": validated_at,
                "status": "valid",
                "fbr_invoice_number": fake_fbr_number,
                "fbr_qr_payload": qr_payload,
                "edit_deadline_at": deadline,
            }
            Invoice.objects.filter(pk=inv.pk).update(**update)
            seeded_valid_invoice_ids.append(inv.pk)

        # ----- 2) Held invoices (no payment, is_held=True) ----------------
        # A held invoice is the "I'm in the middle of ringing this up but
        # need to pause" workflow. Create the invoice with zero payments
        # then flip is_held via the hold() service so the audit log entry
        # mirrors what the React 'Hold' button would produce.
        held_seeded = 0
        for _ in range(opts["held_count"]):
            cart_lines, _ = _build_cart_lines()
            inv = checkout.create_invoice(
                tenant_id=tenant.id, branch=branch, terminal=terminal,
                cashier=cashier, cash_session=None, customer=None,
                cart_lines=cart_lines,
                # Held = unpaid by definition. The model allows zero
                # payments; the React Held-Invoices screen filters by
                # is_held=True regardless of payment state.
                payments=[],
                client_uuid=uuid.uuid4(),
            )
            hold_invoice(inv, label=f"Counter pause #{held_seeded + 1}",
                         user=cashier)
            held_seeded += 1

        # ----- 3) Returns (against the seeded valid invoices) -------------
        # Return one line from each of the first N valid invoices. Those
        # invoices were backdated >72h above so the returns flow takes
        # the credit-note route (no cancel-budget consumption). Refund
        # method cycles through cash + store_credit so the demo shows
        # both rows in the Returns list. Each return triggers a stock
        # movement back to the seeding branch and a refund Payment row.
        return_target = min(return_target, len(seeded_valid_invoice_ids))
        refund_methods = ["cash", "store_credit"]
        for i in range(return_target):
            original = Invoice.objects.get(pk=seeded_valid_invoice_ids[i])
            first_line = SaleItem.objects.filter(invoice=original).first()
            if first_line is None:
                continue
            process_return(
                tenant_id=tenant.id, branch=branch, terminal=terminal,
                cashier=cashier, original_invoice=original,
                items=[{
                    "original_sale_item_id": str(first_line.id),
                    "quantity": str(first_line.quantity),
                    # restocked defaults from reason (customer_changed_mind
                    # → True), but we set it explicitly for clarity.
                    "restocked": True,
                }],
                reason="customer_changed_mind",
                reason_notes="Seed return (demo).",
                refund_method=refund_methods[i % len(refund_methods)],
                client_uuid=uuid.uuid4(),
            )

        self.stdout.write(
            f"Sales: {opts['invoice_count']} invoices, "
            f"{held_seeded} held, {return_target} returns.",
        )

        if reuse_ntn:
            self.stdout.write(self.style.SUCCESS(
                f"Done. Top-up applied to '{tenant.business_name}'. "
                f"Sign in as {owner.email} (existing password).",
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. Sign in as {owner.email} / DemoPass!1",
            ))
