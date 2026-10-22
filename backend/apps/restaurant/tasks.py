"""Scheduled restaurant housekeeping.

The Open Orders screen is the kitchen's live work list. An order leaves it
when the till syncs the paid invoice -- but that makes closure depend on a
terminal reaching the server, and nothing ever cleaned up after a till that
could not. Stale orders therefore piled up day after day: 153 orders worth
PKR 400k across five days, with only the current day's being real.

Staff cannot tell a live table from a five-day-old ghost, and a manual
command is not a fix -- nobody runs it nightly.

This sweeps automatically, after service, every night.
"""

from __future__ import annotations

import datetime as dt
import logging

from celery import shared_task
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# An order in any of these states has been cooked, so after its service day
# it is a completed sale. 'open' means saved-but-never-fired: a draft.
FIRED_STATES = ("sent_to_kitchen", "ready", "served")


@shared_task(name="restaurant.close_stale_open_orders")
def close_stale_open_orders(older_than_days: int = 1) -> dict:
    """Close orders left open after their service day has ended.

    An order that reached the kitchen was cooked and served, so once its day
    is over it is a completed sale, not a live table. Closing it records the
    payment as well -- un-holding alone would make a later sync treat the row
    as an already-finalized duplicate and skip payments and stock, leaving
    the sale permanently unpaid.

    Only orders STRICTLY BEFORE the cut-off are touched, so a table still
    eating tonight is never closed under the guests. An order that never
    reached the kitchen (order_status 'open') is an abandoned draft, not a
    sale, and is left alone -- as is a folio charge, which is internal to a
    stay and is settled by checkout, not by this sweep.

    Safe to run repeatedly: anything already carrying a completed payment is
    skipped.
    """
    from apps.restaurant.services import close_paid_order
    from apps.sales.models import Invoice

    # older_than_days=1 means "yesterday and earlier": yesterday's service
    # has ended, so its orders are finished sales. The cut-off is therefore
    # the first day still considered LIVE, and only dates strictly before it
    # are swept.
    cutoff = timezone.localdate() - dt.timedelta(days=older_than_days - 1)

    stale = (
        Invoice.objects.filter(
            is_held=True,
            deleted_at__isnull=True,
            # Every state that means the kitchen cooked it. 'open' is an
            # un-fired draft and is deliberately excluded.
            order_status__in=FIRED_STATES,
            grand_total__gt=0,
            invoice_date__lt=cutoff,
        )
        .exclude(folio_link__isnull=False)
        .annotate(n_paid=Count("payments", filter=Q(payments__status="completed")))
        .filter(n_paid=0)
        .select_related("terminal")
    )

    closed = 0
    value = 0.0
    for inv in stale:
        try:
            close_paid_order(
                tenant_id=inv.tenant_id, invoice=inv,
                payment_method="cash", user=None,
            )
            closed += 1
            value += float(inv.grand_total or 0)
        except Exception:
            # One bad row must never stop the sweep.
            logger.exception(
                "close_stale_open_orders: failed on %s", inv.local_invoice_number,
            )

    if closed:
        logger.info(
            "close_stale_open_orders: closed %s order(s) worth %.2f (before %s)",
            closed, value, cutoff,
        )
    return {"closed": closed, "value": value, "cutoff": str(cutoff)}
