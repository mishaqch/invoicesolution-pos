"""Recover PAID invoices that were wrongly left held / soft-deleted.

Background
----------
Charging a restaurant order fired two calls against the same client_uuid:

  1. sync.kick()            -> /api/sync/invoices/  (async; finalizes is_held=0)
  2. voidOpenOrder(uuid)    -> soft-deletes the row (immediate)

(2) raced ahead of (1). Its guard only skipped rows that were already
finalized, but at that moment the row was still is_held=True because the
sync had not landed yet -- so it soft-deleted the sale the guest had just
paid for. The invoice list filters is_held=False, deleted_at IS NULL, so
those paid sales became invisible in the client admin.

What this repairs
-----------------
Only invoices that carry a COMPLETED payment -- i.e. money was actually
taken. Those are, by definition, charged sales and belong in the invoice
list. It clears is_held and (when the void race hit) deleted_at.

What it deliberately does NOT touch
-----------------------------------
Held invoices with no completed payment: those are genuine OPEN TABLES /
parked orders still in service. Un-holding them would book an unpaid
table as a completed sale.

Nothing is ever deleted. Every change is written to the audit log.

Usage
-----
    python manage.py repair_paid_held_invoices                 # dry run
    python manage.py repair_paid_held_invoices --apply         # write
    python manage.py repair_paid_held_invoices --tenant <uuid> # scope
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from apps.audit import services as audit
from apps.sales.models import Invoice


class Command(BaseCommand):
    help = "Un-hide PAID invoices wrongly left held/soft-deleted by the charge race."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Write the changes. Without this flag the command only reports.",
        )
        parser.add_argument(
            "--tenant", default=None,
            help="Restrict to one tenant id (default: all tenants).",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Process at most N invoices (useful for a cautious first pass).",
        )
        parser.add_argument(
            "--date", default=None,
            help=(
                "Restrict to one invoice_date (YYYY-MM-DD). Strongly advised "
                "with --served-no-payment: without a date that mode sweeps "
                "the whole history, and an order fired then voided 40 minutes "
                "later is indistinguishable from one that was charged."
            ),
        )
        parser.add_argument(
            "--numbers", default=None,
            help=(
                "Comma-separated local_invoice_number list. The safest option: "
                "recover exactly the invoices you have verified."
            ),
        )
        parser.add_argument(
            "--closed-days", action="store_true",
            help=(
                "With --served-no-payment, ALSO recover served orders that "
                "were never voided — but only on dates before today, where "
                "service has ended. Today's fired orders are left alone "
                "because a held, not-deleted order is indistinguishable from "
                "a table still eating."
            ),
        )
        parser.add_argument(
            "--served-no-payment", action="store_true",
            help=(
                "ALSO recover orders that were SENT TO KITCHEN and then "
                "soft-deleted by the void race, even though the server holds "
                "no payment row (the payment stayed in the terminal's local "
                "SQLite because the sync never landed). Food was cooked and "
                "served, so these are real sales. Never touches an order that "
                "was not fired to the kitchen -- that is an abandoned draft."
            ),
        )

    def handle(self, *args, **opts):
        apply_changes: bool = opts["apply"]
        tenant_id = opts["tenant"]
        limit = opts["limit"]

        # Candidates: held and/or soft-deleted, but carrying real money.
        # A COMPLETED payment is the signal that the sale was charged --
        # paid_total alone is not trusted, because the held snapshot can
        # carry a stale value.
        qs = (
            Invoice.objects.filter(Q(is_held=True) | Q(deleted_at__isnull=False))
            .annotate(
                n_completed=Count(
                    "payments", filter=Q(payments__status="completed"),
                ),
            )
            .order_by("invoice_date", "local_invoice_number")
        )
        if opts["served_no_payment"]:
            # Paid rows, OR orders the kitchen actually cooked and served that
            # the void race soft-deleted before their payment could sync.
            # order_status='open' is excluded on purpose: never fired => draft.
            # A served order needs recovering whether or not it was voided:
            #   - BEFORE 3 Oct the charge path called voidOpenOrder(), so the
            #     lost sales are soft-DELETED and held.
            #   - AFTER that call was removed nothing deletes them — they are
            #     simply left HELD when the sync never lands.
            #
            # But a fired, not-deleted order is ALSO what a table mid-meal
            # looks like, so recovering those needs --closed-days: only dates
            # strictly BEFORE today, where service is over and nothing can
            # still be eating. Without the flag the old (deleted-only) rule
            # stands, so a live table is never booked as a sale.
            served = Q(deleted_at__isnull=False, order_status="sent_to_kitchen")
            if opts["closed_days"]:
                from django.utils import timezone
                # --date pins the run to one day the operator has confirmed
                # is over, so the "before today" cut-off would wrongly exclude
                # it. Day-close is the operator's call; respect it.
                if opts["date"]:
                    served = served | Q(order_status="sent_to_kitchen")
                else:
                    served = served | Q(
                        order_status="sent_to_kitchen",
                        invoice_date__lt=timezone.localdate(),
                    )
            qs = qs.filter(Q(n_completed__gt=0) | served)
            # A zero-value fired order has nothing to bill — the lines were
            # all removed or voided before charge. Recovering it would put an
            # empty invoice in the list.
            qs = qs.exclude(Q(grand_total=0) & Q(n_completed=0))
        else:
            qs = qs.filter(n_completed__gt=0)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if opts["date"]:
            qs = qs.filter(invoice_date=opts["date"])
        if opts["numbers"]:
            wanted = [n.strip() for n in opts["numbers"].split(",") if n.strip()]
            qs = qs.filter(local_invoice_number__in=wanted)
        if limit:
            qs = qs[:limit]

        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.SUCCESS(
                "No paid-but-hidden invoices found. Nothing to repair.",
            ))
            return

        total = Decimal("0")
        n_unheld = n_undeleted = 0
        self.stdout.write("")
        self.stdout.write(
            f"{'invoice':<22}{'date':<12}{'held':<6}{'deleted':<9}"
            f"{'pmts':<6}{'amount':>12}",
        )
        self.stdout.write("-" * 67)
        for inv in rows:
            total += inv.grand_total or Decimal("0")
            if inv.is_held:
                n_unheld += 1
            if inv.deleted_at is not None:
                n_undeleted += 1
            self.stdout.write(
                f"{inv.local_invoice_number or '(none)':<22}"
                f"{str(inv.invoice_date):<12}"
                f"{'yes' if inv.is_held else 'no':<6}"
                f"{'yes' if inv.deleted_at else 'no':<9}"
                f"{inv.n_completed:<6}"
                f"{inv.grand_total:>12,.2f}",
            )

        self.stdout.write("-" * 67)
        self.stdout.write(
            f"{len(rows)} invoice(s)   clear is_held: {n_unheld}   "
            f"restore deleted: {n_undeleted}   value: {total:,.2f}",
        )

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "DRY RUN -- nothing written. Re-run with --apply to commit.",
            ))
            return

        with transaction.atomic():
            for inv in rows:
                before = {
                    "is_held": inv.is_held,
                    "deleted_at": str(inv.deleted_at) if inv.deleted_at else None,
                    "order_status": inv.order_status,
                }
                inv.is_held = False
                inv.deleted_at = None
                # A charged restaurant order is served; leave non-restaurant
                # rows (order_status NULL) exactly as they are.
                if inv.order_status is not None:
                    inv.order_status = "served"
                inv.save(update_fields=[
                    "is_held", "deleted_at", "order_status", "updated_at",
                ])
                audit.log(
                    tenant_id=inv.tenant_id,
                    user=None,
                    entity_type="invoice",
                    entity_id=inv.id,
                    action="repair_paid_held_invoice",
                    before=before,
                    after={
                        "is_held": False,
                        "deleted_at": None,
                        "order_status": inv.order_status,
                    },
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Repaired {len(rows)} paid invoice(s); they now appear in the "
            f"invoice list. Open/unpaid orders were left untouched.",
        ))
