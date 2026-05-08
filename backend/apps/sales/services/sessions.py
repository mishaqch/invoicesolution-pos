"""Cash session open/close.

`expected_amount` = opening_with + (cash sales - cash returns) + cash_in - cash_out
Variance = closed_with - expected_amount.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.sales.models import Invoice, Payment
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
