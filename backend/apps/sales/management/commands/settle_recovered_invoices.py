"""Record the cash payment on invoices recovered from the sync failure.

repair_paid_held_invoices un-hid these sales (cleared is_held / deleted_at)
so they appear in the invoice list, but it never recorded a PAYMENT — the
terminal held that detail and never uploaded it. The result is a finalized
invoice with paid_total = 0, which reads as an unpaid receivable when the
customer in fact paid at the till before leaving.

This settles such an invoice as CASH for its full grand_total, which is the
correct default for a restaurant where the guest pays before leaving. Where
the real tender was card, the method is wrong but the money is right; a
cashier can correct the method afterwards.

Scope guards:
  - only invoices with NO payment rows at all (never double-pays);
  - only ones with grand_total > 0;
  - --date / --terminal / --numbers to keep each run deliberate.

Dry run by default. Every settlement is written to the audit log.

    python manage.py settle_recovered_invoices --terminal "Terminal 2"
    python manage.py settle_recovered_invoices --terminal "Terminal 2" --apply
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from apps.audit import services as audit
from apps.sales.models import Invoice, Payment


class Command(BaseCommand):
    help = "Record the cash payment on recovered invoices left with paid_total = 0."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the changes (default: report only).")
        parser.add_argument("--tenant", default=None, help="Restrict to one tenant id.")
        parser.add_argument("--terminal", default=None,
                            help="Restrict to one terminal NAME, e.g. 'Terminal 2'.")
        parser.add_argument("--date", default=None, help="Restrict to one invoice_date.")
        parser.add_argument("--numbers", default=None,
                            help="Comma-separated local_invoice_number list.")

    def handle(self, *args, **opts):
        qs = (
            Invoice.objects.filter(
                is_held=False, deleted_at__isnull=True, grand_total__gt=0,
            )
            .annotate(n_pay=Count("payments"))
            .filter(n_pay=0)
            .select_related("terminal", "cashier")
            .order_by("invoice_date", "local_invoice_number")
        )
        if opts["tenant"]:
            qs = qs.filter(tenant_id=opts["tenant"])
        if opts["terminal"]:
            qs = qs.filter(terminal__name=opts["terminal"])
        if opts["date"]:
            qs = qs.filter(invoice_date=opts["date"])
        if opts["numbers"]:
            wanted = [n.strip() for n in opts["numbers"].split(",") if n.strip()]
            qs = qs.filter(local_invoice_number__in=wanted)

        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.SUCCESS("Nothing to settle."))
            return

        total = sum((r.grand_total for r in rows), Decimal("0"))
        self.stdout.write("")
        self.stdout.write(f"{'invoice':<24}{'date':<12}{'terminal':<16}{'amount':>12}")
        self.stdout.write("-" * 64)
        for inv in rows[:40]:
            self.stdout.write(
                f"{inv.local_invoice_number or '(none)':<24}"
                f"{str(inv.invoice_date):<12}"
                f"{(inv.terminal.name if inv.terminal_id else '-')[:15]:<16}"
                f"{inv.grand_total:>12,.2f}",
            )
        if len(rows) > 40:
            self.stdout.write(f"... and {len(rows) - 40} more")
        self.stdout.write("-" * 64)
        self.stdout.write(f"{len(rows)} invoice(s)   total: {total:,.2f}")

        if not opts["apply"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "DRY RUN -- nothing written. Re-run with --apply to settle.",
            ))
            return

        with transaction.atomic():
            for inv in rows:
                Payment.objects.create(
                    tenant_id=inv.tenant_id,
                    invoice=inv,
                    customer=inv.customer,
                    payment_method="cash",
                    amount=inv.grand_total,
                    status="completed",
                    received_by=inv.cashier,
                )
                before = {"paid_total": str(inv.paid_total), "status": inv.status}
                inv.paid_total = inv.grand_total
                if inv.status == "pending_sync":
                    inv.status = "finalized"
                inv.save(update_fields=["paid_total", "status", "updated_at"])
                audit.log(
                    tenant_id=inv.tenant_id, user=None,
                    entity_type="invoice", entity_id=inv.id,
                    action="settle_recovered_invoice",
                    before=before,
                    after={"paid_total": str(inv.paid_total), "status": inv.status,
                           "method": "cash"},
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Settled {len(rows)} invoice(s) as cash, total {total:,.2f}.",
        ))
