"""Daily sales summary — gross/tax/net/count per day, optionally per branch.

Source: daily_sales_summary materialized aggregate. Falls back to live
SUM if no aggregate row exists for the requested range (e.g., a tenant
just activated).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from ..base import BaseFilters, ChartSpec, Column, Report
from ..models import DailySalesSummary
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class DailySalesReport(Report):
    name = "daily_sales"
    Filters = _Filters
    columns = (
        Column("date", "Date", "date"),
        Column("branch_name", "Branch"),
        Column("invoice_count", "Invoices", "int", "right"),
        Column("gross", "Gross", "money", "right"),
        Column("tax", "Tax", "money", "right"),
        Column("net", "Net", "money", "right"),
        Column("refund_count", "Refunds", "int", "right"),
        Column("refund_amount", "Refund Rs", "money", "right"),
    )
    chart_spec = ChartSpec(type="line", x_key="date", y_keys=("gross", "net"))

    def _ensure_aggregate(self):
        """Recompute daily_sales_summary for the filtered window so the report is
        always current, independent of the Celery beat schedule."""
        import datetime as _dt

        from apps.tenants.models import Tenant

        from ..aggregates.daily_sales import rebuild_daily_sales

        tenant = Tenant.objects.filter(pk=self.tenant_id).first()
        if tenant is None:
            return
        today = _dt.date.today()
        date_from = self.filters.date_from or (today - _dt.timedelta(days=365))
        date_to = self.filters.date_to or today
        if isinstance(date_from, str):
            date_from = _dt.date.fromisoformat(date_from)
        if isinstance(date_to, str):
            date_to = _dt.date.fromisoformat(date_to)
        try:
            rebuild_daily_sales(tenant, date_from=date_from, date_to=date_to)
        except Exception:  # never let a recompute hiccup break the report read
            pass

    def query(self):
        self._ensure_aggregate()
        qs = DailySalesSummary.objects.for_tenant(self.tenant_id).select_related("branch")
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(date__lte=self.filters.date_to)
        for row in qs.order_by("date", "branch__name"):
            yield {
                "date": row.date,
                "branch_name": row.branch.name,
                "invoice_count": row.invoice_count,
                "gross": row.gross,
                "tax": row.tax,
                "net": row.net,
                "refund_count": row.refund_count,
                "refund_amount": row.refund_amount,
            }

    def totals(self, rows):
        if not rows:
            return {}
        return {
            "invoice_count": sum(r["invoice_count"] for r in rows),
            "gross": sum((r["gross"] for r in rows), Decimal("0")),
            "tax": sum((r["tax"] for r in rows), Decimal("0")),
            "net": sum((r["net"] for r in rows), Decimal("0")),
            "refund_count": sum(r["refund_count"] for r in rows),
            "refund_amount": sum((r["refund_amount"] for r in rows), Decimal("0")),
        }
