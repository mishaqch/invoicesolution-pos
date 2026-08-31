"""Rebuild daily_sales_summary for a (tenant, date) range.

Idempotent: a rerun produces the same numbers. Late-arriving invoices
land on the right day's row because we group by invoice_date, which is
set at sale time.

Counted statuses follow the same set used in the cancel-budget logic:
sales that 'happened' from the books' perspective, including those
that were later cancelled or edited (we do not erase history).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum

from apps.returns.models import Return
from apps.sales.models import Invoice
from apps.tenants.models import Tenant

from ..models import DailySalesSummary


# A sale "counts" the moment it is a COMPLETED (charged, not-held) invoice —
# NOT only after FBR validation. Non-fiscal tenants (fbr_connection_type="none",
# e.g. resorts on PRA) never get an FBR number, so their invoices stay
# "pending_sync"/"submitted" forever; excluding those hid every non-fiscal sale
# from every report. We include them here and rely on the is_held=False /
# deleted_at filters (see rebuild_daily_sales) to keep OPEN orders and drafts
# out. "failed" is deliberately excluded (the sale did not complete).
COUNTED_STATUSES = (
    "pending_sync", "submitted",
    "valid", "edited", "partially_edited", "partially_cancelled",
    "partially_edited_and_cancelled", "finalized", "cancelled",
)

# A narrower set for REVENUE / MARGIN / SPEND / RANKING reports, where a
# fully-cancelled invoice must NOT count (it would inflate a customer's spend,
# a product's revenue/COGS, or the tax base). daily_sales keeps 'cancelled' in
# COUNTED_STATUSES on purpose (audit + count), netting refunds separately.
COUNTED_SALES_STATUSES = tuple(s for s in COUNTED_STATUSES if s != "cancelled")


@transaction.atomic
def rebuild_daily_sales(tenant: Tenant, *, date_from: dt.date, date_to: dt.date) -> int:
    """Rebuild rows for [date_from, date_to] inclusive. Returns rows
    upserted."""

    invoices = (
        Invoice.objects.filter(
            tenant=tenant,
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
            status__in=COUNTED_STATUSES,
            is_held=False,               # exclude OPEN/parked orders — not sales yet
            deleted_at__isnull=True,     # exclude soft-deleted invoices
        )
        .values("branch_id", "invoice_date")
        .annotate(
            gross=Sum("grand_total"),
            tax=Sum("tax_total"),
            count=Count("id"),
        )
    )

    refunds = (
        Return.objects.filter(
            tenant=tenant,
            return_date__gte=date_from,
            return_date__lte=date_to,
        )
        .values("branch_id", "return_date")
        .annotate(
            refund_count=Count("id"),
            refund_amount=Sum("refund_amount"),
        )
    )
    refund_map: dict[tuple[str, dt.date], dict] = {
        (r["branch_id"], r["return_date"]): r for r in refunds
    }

    upserted = 0
    seen: set[tuple[str, dt.date]] = set()
    for row in invoices:
        key = (row["branch_id"], row["invoice_date"])
        seen.add(key)
        gross = row["gross"] or Decimal("0")
        tax = row["tax"] or Decimal("0")
        net = gross - tax
        rk = refund_map.get(key, {})
        DailySalesSummary.objects.update_or_create(
            tenant=tenant, branch_id=row["branch_id"], date=row["invoice_date"],
            defaults={
                "gross": gross,
                "tax": tax,
                "net": net,
                "invoice_count": row["count"],
                "refund_count": rk.get("refund_count") or 0,
                "refund_amount": rk.get("refund_amount") or Decimal("0"),
            },
        )
        upserted += 1

    # Days that had refunds but no invoices still need a row.
    for key, rk in refund_map.items():
        if key in seen:
            continue
        seen.add(key)
        DailySalesSummary.objects.update_or_create(
            tenant=tenant, branch_id=key[0], date=key[1],
            defaults={
                "gross": Decimal("0"),
                "tax": Decimal("0"),
                "net": Decimal("0"),
                "invoice_count": 0,
                "refund_count": rk["refund_count"] or 0,
                "refund_amount": rk["refund_amount"] or Decimal("0"),
            },
        )
        upserted += 1

    # Prune STALE rows: any snapshot row in this window that no longer has a
    # qualifying invoice/refund must be deleted, not left behind. Without this,
    # an invoice that was later voided/held/deleted leaves a phantom sales row
    # that the report keeps showing forever (update_or_create only ever writes).
    stale = DailySalesSummary.objects.filter(
        tenant=tenant, date__gte=date_from, date__lte=date_to,
    )
    for existing in stale.values_list("branch_id", "date"):
        if existing not in seen:
            DailySalesSummary.objects.filter(
                tenant=tenant, branch_id=existing[0], date=existing[1],
            ).delete()

    return upserted
