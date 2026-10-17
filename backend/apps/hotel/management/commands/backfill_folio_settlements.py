"""Give already-closed stays the single invoice they should have had.

Before settlement invoices existed, checkout un-held every FOL- charge and
dumped the whole payment onto one arbitrary "anchor" room. Two consequences
in the live data:

  * 237 internal charge rows (PKR 2.0M) surfaced in the admin invoice list as
    if each were a separate sale, inflating revenue; and
  * 26 invoices carried PKR 321k of payment they had not earned
    (paid_total > grand_total).

This repairs a closed folio to match the new model:

  1. mint ONE real terminal invoice (KK-T2-2026-...) for the stay, carrying
     every live charge line and the settlement payment;
  2. move the payment rows from the old anchor onto it;
  3. re-hold the FOL- charges so they are internal again.

Nothing is deleted. The FOL- rows keep their numbers, items and folio links --
they simply stop masquerading as sales. Idempotent: a folio that already has
a settlement_invoice is skipped, so this is safe to re-run.

    python manage.py backfill_folio_settlements
    python manage.py backfill_folio_settlements --apply
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.hotel.models import GuestFolio
from apps.hotel.services import _build_settlement_invoice


class Command(BaseCommand):
    help = "Mint the missing settlement invoice on already-closed folios."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the changes (default: report only).")
        parser.add_argument("--tenant", default=None, help="Restrict to one tenant id.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Process at most N folios (cautious first pass).")

    def handle(self, *args, **opts):
        qs = (
            GuestFolio.objects.filter(status="closed", settlement_invoice__isnull=True)
            .prefetch_related("charges__invoice__items")
            .order_by("folio_number")
        )
        if opts["tenant"]:
            qs = qs.filter(tenant_id=opts["tenant"])
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        folios = [f for f in qs if f.charges.exists()]
        if not folios:
            self.stdout.write(self.style.SUCCESS("Nothing to backfill."))
            return

        total = Decimal("0")
        self.stdout.write("")
        self.stdout.write(f"{'folio':<20}{'guest':<24}{'charges':>8}{'value':>14}")
        self.stdout.write("-" * 68)
        for i, f in enumerate(folios):
            charges = list(f.charges.select_related("invoice").all())
            value = sum(
                (c.invoice.grand_total or Decimal("0") for c in charges), Decimal("0"),
            )
            total += value
            if i < 25:
                self.stdout.write(
                    f"{f.folio_number:<20}{(f.guest_name or '')[:23]:<24}"
                    f"{len(charges):>8}{value:>14,.2f}",
                )
        if len(folios) > 25:
            self.stdout.write(f"... and {len(folios) - 25} more")
        self.stdout.write("-" * 68)
        self.stdout.write(f"{len(folios)} folio(s)   value: {total:,.2f}")

        if not opts["apply"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "DRY RUN -- nothing written. Re-run with --apply to backfill.",
            ))
            return

        done = 0
        for folio in folios:
            charges = list(folio.charges.select_related("invoice").all())
            if not charges:
                continue
            with transaction.atomic():
                # The old anchor holds the settlement payment rows.
                anchor = next(
                    (c.invoice for c in charges if (c.invoice.paid_total or 0) > 0),
                    None,
                )
                old_payments = list(anchor.payments.all()) if anchor else []
                settled = sum((p.amount for p in old_payments), Decimal("0"))

                invoice = _build_settlement_invoice(
                    folio=folio, charges=charges,
                    cashier=folio.opened_by, payments=[],
                )
                # Re-point the ORIGINAL payment rows rather than creating new
                # ones: the tender, its proof fields and who took it are real
                # history and must survive intact.
                for p in old_payments:
                    p.invoice = invoice
                    p.save(update_fields=["invoice"])
                if settled:
                    invoice.paid_total = settled
                    invoice.save(update_fields=["paid_total", "updated_at"])

                # Charges become internal again.
                for c in charges:
                    inv = c.invoice
                    inv.is_held = True
                    inv.held_label = f"Folio {folio.folio_number}"
                    inv.paid_total = Decimal("0")
                    inv.save(update_fields=[
                        "is_held", "held_label", "paid_total", "updated_at",
                    ])

                folio.settlement_invoice = invoice
                folio.save(update_fields=["settlement_invoice", "updated_at"])
                done += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Backfilled {done} folio(s). Each stay now has ONE invoice; the "
            f"FOL- charge rows are internal again.",
        ))
