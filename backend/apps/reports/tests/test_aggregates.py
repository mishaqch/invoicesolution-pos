"""Tests for the aggregate rebuild functions — the heart of the reports fix.

These lock in the exact semantics that were broken:
  * non-fiscal completed sales (status='pending_sync') MUST count,
  * open orders (is_held=True) and soft-deleted invoices MUST NOT,
  * the daily/velocity snapshots reflect gross/tax/net/COGS correctly,
  * reruns are idempotent.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.reports.aggregates.daily_sales import (
    COUNTED_SALES_STATUSES,
    COUNTED_STATUSES,
    rebuild_daily_sales,
)
from apps.reports.aggregates.product_velocity import rebuild_product_velocity
from apps.reports.models import DailySalesSummary, ProductVelocity

pytestmark = pytest.mark.django_db

TODAY = dt.date.today()
SPAN = dict(date_from=TODAY - dt.timedelta(days=1), date_to=TODAY)


def _summary(tenant, branch):
    return DailySalesSummary.objects.get(tenant=tenant, branch=branch, date=TODAY)


class TestCountedStatuses:
    def test_pending_sync_is_counted(self):
        # The whole bug: non-fiscal sales never leave pending_sync.
        assert "pending_sync" in COUNTED_STATUSES
        assert "submitted" in COUNTED_STATUSES

    def test_cancelled_in_audit_set_but_not_sales_set(self):
        assert "cancelled" in COUNTED_STATUSES
        assert "cancelled" not in COUNTED_SALES_STATUSES

    def test_failed_never_counts(self):
        assert "failed" not in COUNTED_STATUSES


class TestDailySalesRebuild:
    def test_pending_sync_sale_counts(self, tenant, branch, make_invoice):
        make_invoice(status="pending_sync", grand_total=Decimal("100"), tax_total=Decimal("16"))
        n = rebuild_daily_sales(tenant, **SPAN)
        assert n == 1
        row = _summary(tenant, branch)
        assert row.invoice_count == 1
        assert row.gross == Decimal("100")
        assert row.tax == Decimal("16")
        assert row.net == Decimal("84")  # gross - tax

    def test_open_order_excluded(self, tenant, branch, make_invoice):
        make_invoice(is_held=True)  # parked order — not a sale yet
        rebuild_daily_sales(tenant, **SPAN)
        assert not DailySalesSummary.objects.filter(tenant=tenant, date=TODAY).exists()

    def test_soft_deleted_excluded(self, tenant, branch, make_invoice):
        import django.utils.timezone as tz
        make_invoice(deleted_at=tz.now())
        rebuild_daily_sales(tenant, **SPAN)
        assert not DailySalesSummary.objects.filter(tenant=tenant, date=TODAY).exists()

    def test_multiple_invoices_sum(self, tenant, branch, make_invoice):
        make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        make_invoice(grand_total=Decimal("50"), tax_total=Decimal("8"))
        rebuild_daily_sales(tenant, **SPAN)
        row = _summary(tenant, branch)
        assert row.invoice_count == 2
        assert row.gross == Decimal("150")
        assert row.net == Decimal("126")

    def test_rerun_is_idempotent(self, tenant, branch, make_invoice):
        make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        rebuild_daily_sales(tenant, **SPAN)
        rebuild_daily_sales(tenant, **SPAN)
        rows = DailySalesSummary.objects.filter(tenant=tenant, date=TODAY)
        assert rows.count() == 1
        assert rows.first().gross == Decimal("100")

    def test_out_of_window_excluded(self, tenant, branch, make_invoice):
        make_invoice(invoice_date=TODAY - dt.timedelta(days=30))
        rebuild_daily_sales(tenant, **SPAN)
        assert not DailySalesSummary.objects.filter(tenant=tenant).exists()

    def test_stale_row_pruned_when_invoice_becomes_held(self, tenant, branch, make_invoice):
        # A completed sale is snapshotted; then it's re-held (e.g. reverted to an
        # open order). A rebuild must DELETE the now-phantom snapshot row.
        inv = make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        rebuild_daily_sales(tenant, **SPAN)
        assert DailySalesSummary.objects.filter(tenant=tenant, date=TODAY).count() == 1
        inv.is_held = True
        inv.save(update_fields=["is_held"])
        rebuild_daily_sales(tenant, **SPAN)
        assert DailySalesSummary.objects.filter(tenant=tenant, date=TODAY).count() == 0

    def test_stale_row_pruned_when_invoice_soft_deleted(self, tenant, branch, make_invoice):
        import django.utils.timezone as tz
        inv = make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        rebuild_daily_sales(tenant, **SPAN)
        assert DailySalesSummary.objects.filter(tenant=tenant).exists()
        inv.deleted_at = tz.now()
        inv.save(update_fields=["deleted_at"])
        rebuild_daily_sales(tenant, **SPAN)
        assert not DailySalesSummary.objects.filter(tenant=tenant).exists()


class TestProductVelocityRebuild:
    def test_pending_sync_sale_counts(self, tenant, branch, product, make_invoice):
        make_invoice(quantity=Decimal("3"), cost_price=Decimal("60"),
                     grand_total=Decimal("300"), tax_total=Decimal("48"))
        rebuild_product_velocity(tenant, **SPAN)
        pv = ProductVelocity.objects.get(tenant=tenant, product=product, date=TODAY)
        assert pv.quantity == Decimal("3")
        assert pv.revenue == Decimal("300")
        assert pv.cogs == Decimal("180")  # 3 * 60

    def test_open_order_excluded(self, tenant, make_invoice):
        make_invoice(is_held=True, quantity=Decimal("3"))
        rebuild_product_velocity(tenant, **SPAN)
        assert not ProductVelocity.objects.filter(tenant=tenant).exists()

    def test_soft_deleted_excluded(self, tenant, make_invoice):
        import django.utils.timezone as tz
        make_invoice(deleted_at=tz.now(), quantity=Decimal("3"))
        rebuild_product_velocity(tenant, **SPAN)
        assert not ProductVelocity.objects.filter(tenant=tenant).exists()
