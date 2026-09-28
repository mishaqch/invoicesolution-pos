"""Cash session open/close.

`expected_amount` = opening_with + (cash sales - cash returns) + cash_in - cash_out
Variance = closed_with - expected_amount.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.sales.models import Invoice, Payment, SaleItem
from apps.tenants.models import CashSession


@transaction.atomic
def open_session(
    *, tenant_id, branch, terminal, cashier, opening_amount: Decimal,
    request=None,
) -> CashSession:
    if CashSession.objects.filter(terminal=terminal, status="open").exists():
        raise ValidationError(
            {"status": "An open session already exists for this terminal."}
        )
    session = CashSession.objects.create(
        tenant_id=tenant_id,
        branch=branch,
        terminal=terminal,
        cashier=cashier,
        opened_at=timezone.now(),
        opened_with_amount=opening_amount,
    )
    audit_log(
        tenant_id=tenant_id, user=cashier, entity_type="cash_session",
        entity_id=session.id, action="open",
        after={"opening_amount": str(opening_amount)},
        request=request,
    )
    return session


@transaction.atomic
def close_session(
    *, session: CashSession, declared_amount: Decimal, variance_reason: str = "",
    cashier=None, request=None,
) -> CashSession:
    if session.status != "open":
        raise ValidationError({"status": f"Session is {session.status}."})

    locked = CashSession.objects.select_for_update().get(pk=session.pk)
    expected = _compute_expected_amount(locked)
    variance = declared_amount - expected

    locked.closed_at = timezone.now()
    locked.closed_with_amount = declared_amount
    locked.expected_amount = expected
    locked.variance = variance
    locked.variance_reason = variance_reason
    locked.status = "closed"

    # Stash totals for the X-report.
    cash_sales = _cash_sales_for(locked)
    locked.total_sales = cash_sales
    locked.save(update_fields=[
        "closed_at", "closed_with_amount", "expected_amount", "variance",
        "variance_reason", "status", "total_sales", "updated_at",
    ])

    audit_log(
        tenant_id=locked.tenant_id, user=cashier or locked.cashier,
        entity_type="cash_session", entity_id=locked.id, action="close",
        after={
            "expected": str(expected), "declared": str(declared_amount),
            "variance": str(variance),
        },
        request=request,
    )
    return locked


def _cash_sales_for(session: CashSession) -> Decimal:
    invoices = Invoice.objects.filter(cash_session=session)
    cash = (
        Payment.objects.filter(
            invoice__in=invoices, payment_method="cash", status="completed",
        )
        .aggregate(total=Sum("amount"))["total"]
        or Decimal(0)
    )
    return cash


def _compute_expected_amount(session: CashSession) -> Decimal:
    cash = _cash_sales_for(session)
    return (
        session.opened_with_amount
        + cash
        + (session.cash_in or Decimal(0))
        - (session.cash_out or Decimal(0))
    )


# Invoice statuses that represent a COMPLETED sale (not an open/held order, not
# a fully-cancelled one). Non-fiscal tenants (e.g. the TDCP resort) stay on
# "pending_sync" forever, so they must be counted here too.
_SOLD_STATUSES = (
    "pending_sync", "submitted", "valid", "edited",
    "partially_edited", "partially_cancelled",
    "partially_edited_and_cancelled", "finalized",
)


def session_summary(session: CashSession) -> dict:
    """Full end-of-day / Z-report figures for one cash session.

    Covers everything the shift report needs:
      - total_sales      : gross revenue of completed sales in this session
      - total_orders     : count of completed sale invoices
      - total_discount   : sum of discounts given
      - cancelled_orders : invoices fully cancelled in this session
      - cancelled_items  : individual line items cancelled (on any invoice)
      - payment_breakup  : {method: {count, total}} across cash/card/online/…

    Scoped to invoices tied to THIS cash_session, so it reflects exactly what
    the cashier rang up on this shift. Money is Decimal (serialised as string).
    """
    invoices = Invoice.objects.filter(
        cash_session=session, deleted_at__isnull=True, is_held=False,
    )
    data = _summarize_invoices(invoices)
    data.update({
        "session_id": str(session.id),
        "opened_at": session.opened_at.isoformat() if session.opened_at else None,
        "closed_at": session.closed_at.isoformat() if session.closed_at else None,
        "opening_cash": str(session.opened_with_amount or Decimal(0)),
    })
    return data


def daily_summary(*, tenant_id, date, branch=None, terminal=None) -> dict:
    """Full daily summary for a tenant on `date` (Asia/Karachi), optionally
    narrowed to one branch/terminal.

    Date-based (not cash_session-based) so it is robust for tenants whose
    invoices aren't reliably linked to a CashSession (e.g. the TDCP resort,
    where table orders finalise without a session FK). This is what the cashier
    sees as the "Daily Summary" on Day-close / logout.
    """
    invoices = Invoice.objects.filter(
        tenant_id=tenant_id, invoice_date=date,
        deleted_at__isnull=True, is_held=False,
    )
    if branch is not None:
        invoices = invoices.filter(branch=branch)
    if terminal is not None:
        invoices = invoices.filter(terminal=terminal)
    data = _summarize_invoices(invoices)
    data["date"] = date.isoformat()
    return data


def _summarize_invoices(invoices) -> dict:
    """Shared aggregation for the session + daily summaries. `invoices` is an
    already-scoped Invoice queryset (is_held=False, not deleted)."""
    sold = invoices.filter(status__in=_SOLD_STATUSES)

    sold_agg = sold.aggregate(
        total_sales=Sum("grand_total"),
        total_discount=Sum("discount_total"),
        total_tax=Sum("tax_total"),
        orders=Count("id"),
    )

    cancelled_orders = invoices.filter(
        status__in=("cancelled", "partially_cancelled",
                    "partially_edited_and_cancelled"),
    ).count()

    cancelled_items = SaleItem.objects.filter(
        invoice__in=invoices, is_cancelled=True,
    ).count()

    pay_rows = (
        Payment.objects.filter(invoice__in=sold, status="completed")
        .values("payment_method")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("payment_method")
    )
    payment_breakup = {
        r["payment_method"]: {
            "count": r["count"],
            "total": str(r["total"] or Decimal(0)),
        }
        for r in pay_rows
    }

    return {
        "total_sales": str(sold_agg["total_sales"] or Decimal(0)),
        "total_tax": str(sold_agg["total_tax"] or Decimal(0)),
        "total_discount": str(sold_agg["total_discount"] or Decimal(0)),
        "total_orders": sold_agg["orders"] or 0,
        "cancelled_orders": cancelled_orders,
        "cancelled_items": cancelled_items,
        "payment_breakup": payment_breakup,
    }
