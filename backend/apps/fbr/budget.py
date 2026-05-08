"""Cancel-budget service.

Implements the 10% monthly cap from INTEGRATIONS.md §1.10. Atomic
consumption uses select_for_update on the budget row so concurrent
attempts serialize.

PKT timezone is the canonical clock for month boundaries (Pakistan doesn't
observe DST so this is straightforward — but we still go through Django's
timezone-aware utilities for safety).
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.sales.models import Invoice
from apps.tenants.models import Tenant

from .models import (
    FbrCancelBudget,
    FbrCancelBudgetConsumption,
)


CANCEL_BUDGET_RATIO = Decimal("0.10")


class CancelBudgetExceeded(ValidationError):
    """Raised when consume_cancel_budget cannot reserve the requested amount."""


def current_month_start_pkt() -> dt.date:
    """The 1st of the current month in PKT."""
    today_pkt = timezone.localdate()
    return today_pkt.replace(day=1)


def previous_month_range_pkt() -> tuple[dt.date, dt.date]:
    """[first, last_inclusive] of the previous month in PKT."""
    cur = current_month_start_pkt()
    last_prev = cur - dt.timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, last_prev


def compute_edit_deadline(submitted_at: dt.datetime) -> dt.datetime:
    """edit_deadline = MIN(submitted_at + 72h, end_of_month_PKT 23:59:59).

    Per INTEGRATIONS.md §1.9. submitted_at can be any timezone-aware
    datetime; we compute the month-end in PKT to avoid edge-case drift.
    """
    plus_72h = submitted_at + dt.timedelta(hours=72)

    # Convert submitted_at into PKT to find its calendar month, then
    # build the last-second-of-month in PKT.
    pkt = timezone.get_current_timezone()
    local = submitted_at.astimezone(pkt)
    last_day = calendar.monthrange(local.year, local.month)[1]
    end_of_month_pkt = dt.datetime(
        local.year, local.month, last_day, 23, 59, 59, tzinfo=pkt,
    )
    return min(plus_72h, end_of_month_pkt)


# ---------------------------------------------------------------------------
# Budget recomputation (Celery beat at 00:05 PKT on the 1st)
# ---------------------------------------------------------------------------


def recompute_monthly_budget(tenant: Tenant) -> FbrCancelBudget:
    """Compute or refresh THIS month's budget using last month's sales.

    For tenants onboarded mid-month (no last-month sales), the budget is
    Rs 0 — the spec says exactly this. They can issue credit notes
    instead (Phase 6).
    """
    first_prev, last_prev = previous_month_range_pkt()

    # Sum the qualifying invoices' grand totals.
    sales_total: Decimal = (
        Invoice.objects.filter(
            tenant=tenant,
            invoice_date__gte=first_prev,
            invoice_date__lte=last_prev,
            status__in=[
                "valid", "edited", "partially_edited",
                "cancelled", "partially_cancelled",
                "partially_edited_and_cancelled",
                "finalized",
            ],
        )
        .aggregate(total=Sum("grand_total"))["total"]
    ) or Decimal("0")

    budget_amount = (sales_total * CANCEL_BUDGET_RATIO).quantize(Decimal("0.0001"))
    month_start = current_month_start_pkt()

    # Atomic create-or-update. We don't reset consumed_amount on recompute —
    # beat may run twice in the same month. Newly-created rows start at 0;
    # existing rows have their `remaining` recomputed.
    existing = FbrCancelBudget.objects.filter(
        tenant=tenant, month_start=month_start,
    ).first()
    if existing is None:
        return FbrCancelBudget.objects.create(
            tenant=tenant, month_start=month_start,
            previous_month_sales=sales_total,
            budget_amount=budget_amount,
            consumed_amount=Decimal("0"),
            remaining_amount=budget_amount,
        )
    existing.previous_month_sales = sales_total
    existing.budget_amount = budget_amount
    existing.remaining_amount = max(
        Decimal("0"), budget_amount - existing.consumed_amount,
    )
    existing.save(update_fields=[
        "previous_month_sales", "budget_amount",
        "remaining_amount", "last_recalculated_at",
    ])
    return existing


def consume_cancel_budget(
    *, tenant: Tenant, invoice: Invoice, action_type: str, user=None,
) -> FbrCancelBudgetConsumption:
    """Reserve `invoice.grand_total` against this month's budget.

    Raises CancelBudgetExceeded if there isn't enough room.
    select_for_update on the budget row serializes concurrent attempts.

    Note: the lazy-create runs OUTSIDE the consume transaction so that
    a refused consume doesn't roll back the budget row itself — admins
    need to see the row even when the first attempt is over budget.
    """
    if action_type not in ("edit", "cancel"):
        raise ValueError(f"action_type must be 'edit' or 'cancel', got {action_type!r}")

    month_start = current_month_start_pkt()

    # Lazy-create the budget row in its own transaction.
    if not FbrCancelBudget.objects.filter(
        tenant=tenant, month_start=month_start,
    ).exists():
        recompute_monthly_budget(tenant)

    return _consume_inner(tenant=tenant, invoice=invoice, action_type=action_type, user=user)


@transaction.atomic
def _consume_inner(
    *, tenant: Tenant, invoice: Invoice, action_type: str, user=None,
) -> FbrCancelBudgetConsumption:
    month_start = current_month_start_pkt()
    locked = FbrCancelBudget.objects.select_for_update().get(
        tenant=tenant, month_start=month_start,
    )

    requested = Decimal(invoice.grand_total)
    if locked.remaining_amount < requested:
        raise CancelBudgetExceeded(
            f"Cancel budget exceeded. Remaining: Rs. {locked.remaining_amount:.2f}, "
            f"this action requires Rs. {requested:.2f}. "
            f"Use a credit note instead."
        )

    locked.consumed_amount += requested
    locked.remaining_amount -= requested
    locked.save(update_fields=["consumed_amount", "remaining_amount"])

    return FbrCancelBudgetConsumption.objects.create(
        budget=locked,
        invoice=invoice,
        consumption_type=action_type,
        amount=requested,
        consumed_by=user,
    )
