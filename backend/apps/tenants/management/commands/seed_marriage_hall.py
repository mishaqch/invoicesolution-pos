"""Seed a Digital-Invoicing-only marriage-hall demo tenant.

Built to show the DI surface area to someone whose mental model is
"POS = shop with a till". A marriage hall has no till, no cashier,
no inventory; the owner sits at a desk and types up an invoice when
a family books an event, then submits it to FBR like any other
sale.

Creates / tops up:
  - Tenant 'Karachi Events Wedding Hall' with:
        business_mode='digital_invoicing'
        fbr_business_natures=['Service Provider']
        fbr_sector='Services'
        modules_enabled = default DI module set
  - One owner user (no cashier — DI has no till)
  - One 'branch' (the venue itself — DI still needs ≥1 for FK)
  - One hidden terminal row (checkout.create_invoice requires it;
    UI gates Sync/Branches/Terminals out of the sidebar anyway)
  - HS code 9802.9000 'Other services' if not already present
  - One service category, four service Items:
        Hall booking (per event)
        Catering — per head
        Decoration package
        Lighting & sound package
  - Two example customers:
        Khan family (registered, NTN)
        Ahmed family (unregistered walk-in)
  - One sandbox FbrToken aimed at the local mock PRAL gateway
  - N invoices spread across the last 14 days (default 8). Tax 18% GST.

Idempotent: rerunning with the same NTN reuses the tenant. Pass
--wipe to wipe-then-seed in a single command (preserves platform
staff, plan catalog, reference HS codes).

Usage:
    python manage.py seed_marriage_hall --wipe        # nuke + reseed
    python manage.py seed_marriage_hall               # idempotent top-up
    python manage.py seed_marriage_hall --invoice-count 0   # just plumbing
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, HsCode, Product, TaxRate, UnitOfMeasure
from apps.customers.models import Customer
from apps.fbr.models import FbrToken
from apps.fbr.qr import build_qr_payload
from apps.sales.models import Invoice
from apps.sales.services import checkout
from apps.tenants.business_mode import default_modules_for_mode
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal
from apps.tenants.modules import normalise as normalise_modules


# Four service "items" the marriage hall would sell. Per-event prices
# in PKR. cost_price = the hall's bare-bones outlay (vendor charges,
# food cost, etc.), sale_price = what the family is invoiced.
_ITEMS = [
    # name, sku, sale, cost, uom, description
    ("Hall booking — main event", "HALL-MAIN", "200000", "60000", "PCS",
     "Use of main hall for one evening (6pm – midnight)."),
    ("Catering — per head", "CATR-HEAD", "1800", "950", "PCS",
     "Catered buffet meal, per attendee. Min 100 heads."),
    ("Decoration package — Premium", "DECOR-PREM", "85000", "32000", "PCS",
     "Stage, entry, hall lighting + floral arrangements."),
    ("Lighting & sound package", "LITE-SOUND", "45000", "18000", "PCS",
     "Stage lights, sound system + operator for 5 hours."),
]


# HS code marriage halls actually file under in Pakistan. FBR's "Other
# services" bucket. Not in the default HS seed (which is goods-only)
# so we ensure it on first run.
_SERVICES_HS = ("9802.9000", "Other services (banquet halls, event venues)")


class Command(BaseCommand):
    help = (
        "Seed a marriage-hall demo tenant to showcase the Digital "
        "Invoicing experience for service providers."
    )

    def add_arguments(self, parser):
        parser.add_argument("--ntn", default="3399887766")
        parser.add_argument(
            "--business-name", default="Karachi Events Wedding Hall",
        )
        parser.add_argument(
            "--owner-email", default="owner@karachi-events.example",
        )
        parser.add_argument(
            "--invoice-count", type=int, default=8,
            help="How many past invoices to seed (default 8, spread over 14 days).",
        )
        parser.add_argument(
            "--wipe", action="store_true",
            help=(
                "Run `wipe_tenant_data --confirm` before seeding. "
                "Removes all tenants + tenant data + non-platform users. "
                "Preserves platform staff, plan catalog, HS codes."
            ),
        )

    def handle(self, *args, **opts):
        # NB: this method intentionally is NOT wrapped in @transaction.atomic.
        # wipe_tenant_data is itself atomic; nesting our atomic on top
        # turns the wipe into a savepoint that rolls back if any later
        # step (seeding) raises. The seed step has its own atomic
        # block via _seed() below — that's the right granularity.
        if opts["wipe"]:
            # Wipe everything first so the marriage hall is the only
            # tenant left. wipe_tenant_data is its own transaction
            # and commits before we return.
            self.stdout.write("Wiping existing tenant data…")
            buf = StringIO()
            call_command("wipe_tenant_data", "--confirm", stdout=buf)
            for line in buf.getvalue().splitlines():
                self.stdout.write(f"  {line}")
        self._seed(opts)

    @transaction.atomic
    def _seed(self, opts):

        User = get_user_model()

        # ---- Tenant ---------------------------------------------------------
        tenant, created = Tenant.objects.get_or_create(
            ntn=opts["ntn"],
            defaults={
                "business_name": opts["business_name"],
                "business_type": "sole_proprietor",
                # Marriage halls are based in cities; pick Sindh + Karachi
                # so the buyer/seller province field has a realistic value.
                "province": "SINDH",
                "business_mode": "digital_invoicing",
                "fbr_business_natures": ["Service Provider"],
                "fbr_sector": "Services",
                # default_modules_for_mode returns the DI module set
                # (sales/fbr/customers/dcn/manual_amendments/reports_basic/audit_log).
                # normalise_modules guarantees forced modules are present
                # and the list is deduped.
                "modules_enabled": normalise_modules(
                    default_modules_for_mode("digital_invoicing"),
                ),
            },
        )
        if not created:
            # Top-up: ensure the DI flags are still set even if the
            # operator clicked through the wizard differently on a
            # prior run.
            dirty = False
            if tenant.business_mode != "digital_invoicing":
                tenant.business_mode = "digital_invoicing"; dirty = True
            if tenant.fbr_business_natures != ["Service Provider"]:
                tenant.fbr_business_natures = ["Service Provider"]; dirty = True
            if tenant.fbr_sector != "Services":
                tenant.fbr_sector = "Services"; dirty = True
            if dirty:
                tenant.save(update_fields=[
                    "business_mode", "fbr_business_natures", "fbr_sector",
                ])
        self.stdout.write(
            f"Tenant: {tenant.business_name} (ntn={tenant.ntn}, "
            f"mode={tenant.business_mode})",
        )

        # ---- Owner user -----------------------------------------------------
        owner, _ = User.objects.get_or_create(
            email=opts["owner_email"],
            defaults={"full_name": "Adeel Khan"},
        )
        owner.set_password("DemoPass!1")
        # DI tenants don't run a till so no PIN is required for the owner.
        owner.save()
        TenantMembership.objects.get_or_create(
            tenant=tenant, user=owner, defaults={"role": "owner"},
        )

        # ---- Branch + (hidden) terminal -------------------------------------
        # checkout.create_invoice requires branch + terminal FKs. For a
        # DI tenant we still need the rows but the sidebar hides
        # Branches/Sync/Hardware — the operator never sees them.
        branch, _ = Branch.objects.get_or_create(
            tenant=tenant, code="MAIN",
            defaults={
                "name": "Main venue",
                "address": "Plot 14, Tipu Sultan Road, Karachi",
                "city": "Karachi",
                "province": "SINDH",
                "is_default": True,
            },
        )
        Terminal.objects.get_or_create(
            tenant=tenant, name="Office desk",
            defaults={
                "branch": branch,
                # device_fingerprint must be globally unique. Salt
                # with the tenant NTN so reruns don't collide.
                "device_fingerprint": f"di-seed-{tenant.ntn}-{uuid.uuid4().hex[:6]}",
            },
        )

        # ---- HS code 9802.9000 (services) -----------------------------------
        # The goods-only HS seed doesn't ship a services code. Create
        # it on demand so every Item line we attach is FBR-shaped.
        hs_code, _ = HsCode.objects.get_or_create(
            code=_SERVICES_HS[0],
            defaults={"description": _SERVICES_HS[1], "default_tax_rate": 18},
        )

        # ---- Tax rate (single sector-wide 18% — DI tenants don't juggle rates)
        tax_rate, _ = TaxRate.objects.get_or_create(
            tenant=tenant, name="GST 18%",
            defaults={
                "rate": Decimal("18.00"),
                "is_default": True,
                "applies_to": "services",
            },
        )

        # ---- Category + items -----------------------------------------------
        category, _ = Category.objects.get_or_create(
            tenant=tenant, slug="event-services",
            defaults={"name": "Event services"},
        )
        uom = UnitOfMeasure.objects.get(code="PCS")
        for name, sku, sale, cost, _uom_code, _desc in _ITEMS:
            Product.objects.get_or_create(
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
                    # No reorder_level / opening stock: services don't
                    # have inventory.
                },
            )
        self.stdout.write(
            f"Catalog: {Product.objects.filter(tenant=tenant, deleted_at__isnull=True).count()} "
            f"service items.",
        )

        # ---- Customers ------------------------------------------------------
        # One registered NTN-holding family (the FBR builder treats this
        # as B2B and emits the full buyer block). One walk-in family
        # (FBR builder substitutes the 13-zero CNIC sentinel).
        khan, _ = Customer.objects.get_or_create(
            tenant=tenant, customer_code="F001",
            defaults={
                "name": "Khan family (Mr. Tariq Khan)",
                "ntn": "1122334",
                "registration_type": "registered",
                "phone": "+92-300-1122334",
                "address": "House 22, DHA Phase 6, Karachi",
                "province": "SINDH",
            },
        )
        Customer.objects.get_or_create(
            tenant=tenant, customer_code="F002",
            defaults={
                "name": "Ahmed family (walk-in)",
                "phone": "+92-321-7788991",
                "registration_type": "unregistered",
                "province": "SINDH",
            },
        )

        # ---- FBR sandbox token (points at the local mock gateway) -----------
        # The mock at /__mock_pral/* behaves like PRAL: validates
        # payload shape, returns a synthetic FBR invoice number. The
        # FBR client appends "/postinvoicedata_sb" itself for sandbox,
        # so the api_endpoint here is the gateway root.
        mock_endpoint = "http://localhost:8000/__mock_pral"
        if not FbrToken.objects.filter(tenant=tenant, environment="sandbox").exists():
            tok = FbrToken(
                tenant=tenant, environment="sandbox",
                api_endpoint=mock_endpoint, is_active=True,
            )
            tok.token = "DEV-MOCK-TOKEN"
            tok.save()

        # ---- Invoices -------------------------------------------------------
        # Realistic-ish booking pattern: most invoices pick "Hall +
        # Catering + Decoration" together (the booking bundle), occasional
        # à-la-carte invoices for just lights/decor. Spread across the
        # last 14 days.
        products = list(
            Product.objects.filter(tenant=tenant, deleted_at__isnull=True),
        )
        if not products:
            raise SystemExit("No products — cannot seed invoices.")
        terminal = Terminal.objects.filter(tenant=tenant).first()
        customer_pool = list(Customer.objects.filter(tenant=tenant))

        random.seed(73)
        now = timezone.now()
        invoice_count = opts["invoice_count"]
        if invoice_count > 0:
            self.stdout.write(f"Seeding {invoice_count} demo invoices…")

        for i in range(invoice_count):
            # Bundle pick: 60% chance of the full booking, 40% one-off.
            if random.random() < 0.6:
                picks = [p for p in products if p.sku in
                         ("HALL-MAIN", "CATR-HEAD", "DECOR-PREM")]
                # Catering line gets a realistic head count.
                cart_lines = []
                for p in picks:
                    qty = random.randint(120, 300) if p.sku == "CATR-HEAD" else 1
                    cart_lines.append({
                        "product": str(p.id),
                        "quantity": str(qty),
                        "unit_price": str(p.sale_price),
                        "tax_rate": "18",
                        "is_taxable": True,
                    })
            else:
                # À-la-carte: pick something with a sensible unit price.
                # Catering-per-head sold as qty=1 looks like a single
                # plated meal invoice (silly), so exclude it from the
                # one-off pool — that line only makes sense in the
                # bundle case where qty is the head count.
                alacarte_pool = [p for p in products if p.sku != "CATR-HEAD"]
                p = random.choice(alacarte_pool)
                cart_lines = [{
                    "product": str(p.id),
                    "quantity": "1",
                    "unit_price": str(p.sale_price),
                    "tax_rate": "18",
                    "is_taxable": True,
                }]
            total = sum(
                Decimal(line["quantity"]) * Decimal(line["unit_price"])
                * Decimal("1.18")
                for line in cart_lines
            )
            # 70% of invoices are to a known family (one of the two
            # customers); 30% are walk-in / no customer attached.
            customer = random.choice(customer_pool) if random.random() < 0.7 else None
            inv = checkout.create_invoice(
                tenant_id=tenant.id, branch=branch, terminal=terminal,
                cashier=owner, cash_session=None, customer=customer,
                cart_lines=cart_lines,
                # Half the bookings pay by bank transfer (the realistic
                # advance + balance flow); the rest pay cash. Bank
                # transfer requires bank_name + bank_reference per the
                # payments adapter contract.
                payments=[(
                    {
                        "payment_method": "bank_transfer",
                        "amount": str(total),
                        "bank_name": "HBL",
                        "bank_reference": f"WED-{i:04d}",
                    } if i % 2 == 0 else
                    {"payment_method": "cash", "amount": str(total)}
                )],
                client_uuid=uuid.uuid4(),
            )

            offset_days = random.randint(0, 13)
            validated_at = now - timezone.timedelta(days=offset_days)
            # Fake the post-PRAL state so the invoice detail page
            # renders a QR. PRAL invoice numbers are 18 digits; this
            # mirrors the sandbox shape closely enough for demo.
            fake_fbr_number = f"7{tenant.ntn.rjust(13, '0')[:13]}{i:04d}"
            qr_payload = build_qr_payload(
                fbr_invoice_number=fake_fbr_number,
                validated_at=validated_at,
                amount=inv.grand_total,
                seller_ntn=tenant.ntn,
            )
            deadline = validated_at + timezone.timedelta(hours=72)
            Invoice.objects.filter(pk=inv.pk).update(
                invoice_date=timezone.localdate()
                - timezone.timedelta(days=offset_days),
                created_at=validated_at,
                status="valid",
                fbr_invoice_number=fake_fbr_number,
                fbr_qr_payload=qr_payload,
                edit_deadline_at=deadline,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done. Sign in as {owner.email} / DemoPass!1",
        ))
