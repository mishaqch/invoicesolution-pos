"""Cancel budget — atomicity, exhaustion, edge cases."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.fbr.budget import (
    CancelBudgetExceeded,
    compute_edit_deadline,
    consume_cancel_budget,
    current_month_start_pkt,
    recompute_monthly_budget,
)
from apps.fbr.models import FbrCancelBudget, FbrCancelBudgetConsumption
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="X", code="BX",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="bud-fp",
    )


def _invoice(tenant, branch, terminal, cashier, *, grand_total: str, when: dt.date | None = None,
              status: str = "valid"):
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=cashier,
        local_invoice_number=f"BX-T1-2026-{uuid.uuid4().hex[:7]}",
        invoice_date=when or dt.date.today(),
        subtotal=Decimal(grand_total),
        grand_total=Decimal(grand_total),
        paid_total=Decimal(grand_total),
        status=status,
        client_uuid=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# recompute_monthly_budget
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_budget_zero_when_no_history(tenant, branch, terminal, owner_user):
    """Tenant onboarded mid-month with no last-month sales → Rs 0 budget."""
    budget = recompute_monthly_budget(tenant)
    assert budget.previous_month_sales == Decimal("0")
    assert budget.budget_amount == Decimal("0")
    assert budget.remaining_amount == Decimal("0")


@pytest.mark.django_db
def test_budget_is_10pct_of_last_month_sales(tenant, branch, terminal, owner_user):
    # Place a sale in the previous month
    first_prev = current_month_start_pkt() - dt.timedelta(days=1)
    first_prev = first_prev.replace(day=1)
    _invoice(tenant, branch, terminal, owner_user, grand_total="10000",
             when=first_prev)
    budget = recompute_monthly_budget(tenant)
    assert budget.previous_month_sales == Decimal("10000.0000")
    assert budget.budget_amount == Decimal("1000.0000")  # 10% of 10000
    assert budget.remaining_amount == Decimal("1000.0000")


# ---------------------------------------------------------------------------
# consume_cancel_budget
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_consume_budget_decrements_remaining(tenant, branch, terminal, owner_user):
    budget = FbrCancelBudget.objects.create(
        tenant=tenant, month_start=current_month_start_pkt(),
        previous_month_sales=Decimal("10000"),
        budget_amount=Decimal("1000"),
        consumed_amount=Decimal("0"),
        remaining_amount=Decimal("1000"),
    )
    inv = _invoice(tenant, branch, terminal, owner_user, grand_total="300")
    consume_cancel_budget(
        tenant=tenant, invoice=inv, action_type="cancel", user=owner_user,
    )
    budget.refresh_from_db()
    assert budget.consumed_amount == Decimal("300.0000")
    assert budget.remaining_amount == Decimal("700.0000")
    assert FbrCancelBudgetConsumption.objects.filter(invoice=inv).count() == 1


@pytest.mark.django_db
def test_consume_refused_when_exhausted(tenant, branch, terminal, owner_user):
    FbrCancelBudget.objects.create(
        tenant=tenant, month_start=current_month_start_pkt(),
        previous_month_sales=Decimal("10000"),
        budget_amount=Decimal("1000"),
        consumed_amount=Decimal("900"),
        remaining_amount=Decimal("100"),
    )
    inv = _invoice(tenant, branch, terminal, owner_user, grand_total="500")
    with pytest.raises(CancelBudgetExceeded):
        consume_cancel_budget(
            tenant=tenant, invoice=inv, action_type="cancel", user=owner_user,
        )
    # No consumption row was written.
    assert FbrCancelBudgetConsumption.objects.filter(invoice=inv).count() == 0


@pytest.mark.django_db
def test_consume_creates_budget_lazily_when_missing(
    tenant, branch, terminal, owner_user,
):
    """If beat hasn't run yet for this month, consume creates a Rs 0 budget
    on the fly, then refuses the consume."""
    inv = _invoice(tenant, branch, terminal, owner_user, grand_total="100")
    with pytest.raises(CancelBudgetExceeded):
        consume_cancel_budget(
            tenant=tenant, invoice=inv, action_type="cancel", user=owner_user,
        )
    assert FbrCancelBudget.objects.filter(tenant=tenant).count() == 1


# ---------------------------------------------------------------------------
# compute_edit_deadline (timezone math)
# ---------------------------------------------------------------------------


def test_deadline_within_72h_when_far_from_month_end():
    submitted = dt.datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.get_current_timezone())
    deadline = compute_edit_deadline(submitted)
    expected_72h = submitted + dt.timedelta(hours=72)
    assert deadline == expected_72h  # 4 May 10:00 PKT


def test_deadline_clamped_to_month_end_when_close():
    submitted = dt.datetime(2026, 5, 30, 23, 59, tzinfo=timezone.get_current_timezone())
    deadline = compute_edit_deadline(submitted)
    # 72h would be 2 Jun 23:59; clamped to 31 May 23:59:59 PKT
    assert deadline.month == 5
    assert deadline.day == 31
    assert deadline.hour == 23 and deadline.minute == 59


def test_deadline_at_exact_month_boundary():
    submitted = dt.datetime(2026, 5, 31, 23, 59, tzinfo=timezone.get_current_timezone())
    deadline = compute_edit_deadline(submitted)
    # End of month is essentially same minute; 72h beats that, clamp wins.
    assert deadline.month == 5 and deadline.day == 31


def test_deadline_february_28_2026():
    """2026 is not a leap year; Feb has 28 days."""
    submitted = dt.datetime(2026, 2, 28, 12, 0, tzinfo=timezone.get_current_timezone())
    deadline = compute_edit_deadline(submitted)
    assert deadline.month == 2 and deadline.day == 28
