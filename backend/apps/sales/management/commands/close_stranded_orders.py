"""Close served open orders that a terminal could never sync.

When a till cannot reach /api/sync/invoices/ — an old build, a lost auth
token, a reinstalled machine — the guest pays and leaves but the order stays
is_held=True forever: invisible to reports and the invoice list, and stuck on
the Open orders screen. At TDCP that stranded 170 orders worth PKR 424k in a
single week.

This closes them server-side AND records the payment, which is the part that
matters: un-holding alone would make a later sync treat the row as an
already-finalized duplicate and skip payments and stock, leaving the sale
permanently unpaid.

Only SERVED orders qualify (order_status='sent_to_kitchen') — the kitchen
cooked the food, so the guest was billed. An order never fired is a draft and
is left alone. Anything that already carries a completed payment is skipped,
so this is safe to re-run and safe if the till later syncs on its own.

    python manage.py close_stranded_orders --terminal "Terminal 2"
    python manage.py close_stranded_orders --terminal "Terminal 2" --apply
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.restaurant.services import close_paid_order
from apps.sales.models import Invoice


class Command(BaseCommand):
    help = "Close + settle served open orders a terminal never managed to sync."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the changes (default: report only).")
        parser.add_argument("--terminal", default=None,
                            help="Restrict to one terminal NAME, e.g. 'Terminal 2'.")
        parser.add_argument("--branch", default=None, help="Restrict to one branch CODE.")
        parser.add_argument("--before", default=None,
                            help="Only orders with invoice_date < this (YYYY-MM-DD). "
                                 "Use it to protect a day still in service.")
        parser.add_argument("--method", default="cash",
                            help="Payment method to record (default: cash).")

    def handle(self, *args, **opts):
        qs = (
            Invoice.objects.filter(
                is_held=True, deleted_at__isnull=True,
                order_status="sent_to_kitchen", grand_total__gt=0,
            )
            .annotate(n_paid=Count("payments", filter=Q(payments__status="completed")))
            .filter(n_paid=0)
            .select_related("terminal", "branch")
            .order_by("invoice_date", "local_invoice_number")
        )
        if opts["terminal"]:
            qs = qs.filter(terminal__name=opts["terminal"])
        if opts["branch"]:
            qs = qs.filter(branch__code=opts["branch"])
        if opts["before"]:
            qs = qs.filter(invoice_date__lt=opts["before"])

        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.SUCCESS("No stranded orders found."))
            return

        total = sum((r.grand_total for r in rows), Decimal("0"))
        self.stdout.write("")
        self.stdout.write(f"{'invoice':<24}{'date':<12}{'terminal':<16}{'amount':>12}")
        self.stdout.write("-" * 64)
        for inv in rows[:30]:
            self.stdout.write(
                f"{inv.local_invoice_number or '(none)':<24}"
                f"{str(inv.invoice_date):<12}"
                f"{(inv.terminal.name if inv.terminal_id else '-')[:15]:<16}"
                f"{inv.grand_total:>12,.2f}",
            )
        if len(rows) > 30:
            self.stdout.write(f"... and {len(rows) - 30} more")
        self.stdout.write("-" * 64)
        self.stdout.write(f"{len(rows)} order(s)   total: {total:,.2f}")

        if not opts["apply"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "DRY RUN -- nothing written. Re-run with --apply to close them.",
            ))
            return

        closed = 0
        for inv in rows:
            close_paid_order(
                tenant_id=inv.tenant_id, invoice=inv,
                payment_method=opts["method"], user=None,
            )
            closed += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Closed {closed} order(s) as {opts['method']}, total {total:,.2f}. "
            f"They now appear in the invoice list and reports.",
        ))
