"""Behavioural + filter tests for the reports fixed in this change.

Covers the two things the smoke net can't:
  * the on-demand aggregate refresh — a report returns data even when the
    Celery beat task never ran (the original bug),
  * filter application — branch_id and date_from/date_to actually narrow
    the result set.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.reports.models import DailySalesSummary
from apps.reports.registry import get

pytestmark = pytest.mark.django_db

TODAY = dt.date.today()


def _run(name, tenant, **filter_kwargs):
    R = get(name)
    rep = R(tenant_id=str(tenant.id), filters=R.Filters(**filter_kwargs))
    return rep.run(use_cache=False)


class TestOnDemandRefresh:
    """The core regression: reports must not depend on the beat task."""

    def test_daily_sales_populates_without_precomputed_aggregate(self, tenant, make_invoice):
        make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        # No rebuild_daily_sales() called by the test — the report must do it.
        assert not DailySalesSummary.objects.filter(tenant=tenant).exists()
        result = _run("daily_sales", tenant)
        assert result.row_count == 1
        assert result.rows[0]["gross"] == Decimal("100")
        # And the snapshot got written as a side effect.
        assert DailySalesSummary.objects.filter(tenant=tenant).exists()

    def test_item_wise_populates_without_precomputed_aggregate(self, tenant, make_invoice):
        make_invoice(quantity=Decimal("2"), grand_total=Decimal("200"), tax_total=Decimal("32"))
        result = _run("item_wise", tenant)
        assert result.row_count >= 1

    def test_profit_loss_computes_margin(self, tenant, make_invoice):
        # revenue 300 (tax 48), cogs 3*60=180 → margin present
        make_invoice(quantity=Decimal("3"), cost_price=Decimal("60"),
                     grand_total=Decimal("300"), tax_total=Decimal("48"))
        result = _run("profit_loss", tenant)
        assert "revenue" in result.totals
        assert "cogs" in result.totals
        assert result.totals["cogs"] == Decimal("180")


class TestFilters:
    def test_branch_filter_narrows_daily_sales(self, tenant, branch, branch2, make_invoice):
        make_invoice(the_branch=branch, grand_total=Decimal("100"), tax_total=Decimal("16"))
        make_invoice(the_branch=branch2, grand_total=Decimal("50"), tax_total=Decimal("8"))
        all_rows = _run("daily_sales", tenant)
        assert all_rows.row_count == 2  # one row per branch
        only_b1 = _run("daily_sales", tenant, branch_id=str(branch.id))
        assert only_b1.row_count == 1
        assert only_b1.rows[0]["gross"] == Decimal("100")

    def test_date_filter_narrows_daily_sales(self, tenant, make_invoice):
        make_invoice(invoice_date=TODAY, grand_total=Decimal("100"), tax_total=Decimal("16"))
        make_invoice(invoice_date=TODAY - dt.timedelta(days=5),
                     grand_total=Decimal("40"), tax_total=Decimal("6"))
        today_only = _run("daily_sales", tenant, date_from=TODAY, date_to=TODAY)
        assert today_only.row_count == 1
        assert today_only.rows[0]["gross"] == Decimal("100")

    def test_date_filter_empty_when_out_of_range(self, tenant, make_invoice):
        make_invoice(invoice_date=TODAY, grand_total=Decimal("100"))
        future = TODAY + dt.timedelta(days=10)
        res = _run("daily_sales", tenant, date_from=future, date_to=future)
        assert res.row_count == 0

    def test_totals_sum_rows(self, tenant, branch, branch2, make_invoice):
        make_invoice(the_branch=branch, grand_total=Decimal("100"), tax_total=Decimal("16"))
        make_invoice(the_branch=branch2, grand_total=Decimal("50"), tax_total=Decimal("8"))
        res = _run("daily_sales", tenant)
        assert res.totals["gross"] == Decimal("150")
        assert res.totals["invoice_count"] == 2


class TestExcludedFromReports:
    def test_open_order_absent_from_daily_sales(self, tenant, make_invoice):
        make_invoice(is_held=True, grand_total=Decimal("999"))
        res = _run("daily_sales", tenant)
        assert res.row_count == 0

    def test_soft_deleted_absent_from_daily_sales(self, tenant, make_invoice):
        import django.utils.timezone as tz
        make_invoice(deleted_at=tz.now(), grand_total=Decimal("999"))
        res = _run("daily_sales", tenant)
        assert res.row_count == 0


class TestDashboardInvoiceCount:
    """The dashboard 'Invoices' KPI must count only REAL invoices — the same
    set the invoice list shows — not held/parked orders (tablet ORD-…, folio
    FOL-…) or soft-deleted drafts. Regression: it filtered only status__in and
    over-counted (2026-09-04)."""

    def _totals(self, tenant):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from django.contrib.auth import get_user_model
        from apps.reports.views import dashboard_view

        user = get_user_model().objects.filter(
            memberships__tenant=tenant,
        ).first() or get_user_model().objects.create(email="d@t.pk", full_name="D")
        req = APIRequestFactory().get("/api/reports/dashboard/")
        force_authenticate(req, user=user)
        req.tenant_id = str(tenant.id)
        resp = dashboard_view(req)
        assert resp.status_code == 200, resp.data
        return resp.data["totals"]

    def test_count_excludes_held_and_deleted(self, tenant, make_invoice):
        make_invoice(status="finalized")                      # real ✓
        make_invoice(status="valid")                          # real ✓
        make_invoice(status="pending_sync", is_held=True)     # parked/tablet order ✗
        make_invoice(status="pending_sync", deleted_at=dt.datetime(2026, 9, 4)) # deleted ✗
        totals = self._totals(tenant)
        assert totals["invoices_total"] == 2, totals["invoices_total"]

    def test_month_count_excludes_held(self, tenant, make_invoice):
        today = dt.date.today()
        make_invoice(status="finalized", invoice_date=today)                 # ✓
        make_invoice(status="pending_sync", is_held=True, invoice_date=today) # ✗
        totals = self._totals(tenant)
        assert totals["invoices_month_count"] == 1, totals["invoices_month_count"]
