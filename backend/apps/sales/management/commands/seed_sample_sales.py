"""Seed sample invoices for the admin sales list UI verification.

Until Phase 3 wires real POS→server sync, the admin web has no invoices
to display. This command creates a few realistic ones server-side so the
sales list, invoice detail, and cancel flow can be exercised.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Product
from apps.inventory.services.movements import record_movement
from apps.sales.services import checkout
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal


class Command(BaseCommand):
    help = "Seed N sample invoices for a tenant (verification helper)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True,
                            help="Tenant NTN (e.g. 1234567)")
        parser.add_argument("--count", type=int, default=10)
        parser.add_argument("--branch-code", default=None,
                            help="Branch code (defaults to first active branch)")

    def handle(self, *args, **opts):
        tenant = self._tenant(opts["tenant"])
        branch = self._branch(tenant, opts.get("branch_code"))
        terminal = self._terminal(tenant, branch)
        cashier = self._cashier(tenant)

        products = list(Product.objects.filter(tenant=tenant, is_active=True)[:10])
        if not products:
            raise CommandError("Tenant has no active products. Add some first.")

        # Make sure each chosen product has stock so the sale movement is valid.
        for p in products:
            record_movement(
                tenant_id=tenant.id, product=p, branch=branch,
                movement_type="opening_balance",
                quantity=Decimal("100"),
                reason="seed_sample_sales",
            )

        created = 0
        with transaction.atomic():
            for i in range(opts["count"]):
                lines = []
                for _ in range(random.randint(1, 3)):
                    p = random.choice(products)
                    qty = random.choice([1, 1, 1, 2, 3])
                    lines.append({
                        "product": str(p.id),
                        "quantity": str(qty),
                        "unit_price": str(p.sale_price),
                        "tax_rate": "18" if p.is_taxable else "0",
                        "is_taxable": p.is_taxable,
                    })
                grand = sum(
                    Decimal(line["unit_price"]) * Decimal(line["quantity"])
                    * (Decimal("1.18") if line["is_taxable"] else Decimal(1))
                    for line in lines
                )
                checkout.create_invoice(
                    tenant_id=tenant.id, branch=branch, terminal=terminal,
                    cashier=cashier, cash_session=None, customer=None,
                    cart_lines=lines,
                    payments=[{"payment_method": "cash", "amount": str(grand)}],
                    client_uuid=str(uuid.uuid4()),
                    notes=f"seed sample {i+1}",
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {created} sample invoices for {tenant.business_name}."
        ))

    def _tenant(self, ntn) -> Tenant:
        try:
            return Tenant.objects.get(ntn=ntn)
        except Tenant.DoesNotExist:
            raise CommandError(f"No tenant with NTN={ntn}")

    def _branch(self, tenant, code) -> Branch:
        qs = Branch.objects.filter(tenant=tenant, deleted_at__isnull=True)
        if code:
            try:
                return qs.get(code=code)
            except Branch.DoesNotExist:
                raise CommandError(f"No branch with code={code}")
        b = qs.first()
        if not b:
            raise CommandError("Tenant has no branches.")
        return b

    def _terminal(self, tenant, branch) -> Terminal:
        t = Terminal.objects.filter(tenant=tenant, branch=branch, is_active=True).first()
        if t:
            return t
        return Terminal.objects.create(
            tenant=tenant, branch=branch, name="Counter 1",
            device_fingerprint=f"seed-{uuid.uuid4().hex[:8]}",
        )

    def _cashier(self, tenant):
        User = get_user_model()
        membership = TenantMembership.objects.filter(
            tenant=tenant, role__in=("cashier", "manager", "owner"),
        ).select_related("user").first()
        if not membership:
            raise CommandError("Tenant has no users.")
        return membership.user
