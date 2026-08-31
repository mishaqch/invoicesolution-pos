"""Daily sales summary — gross/tax/net/count per day, optionally per branch.

Source: daily_sales_summary materialized aggregate. Falls back to live
SUM if no aggregate row exists for the requested range (e.g., a tenant
just activated).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from ..aggregates.ensure import EnsuresDailySales
from ..base import BaseFilters, ChartSpec, Column, Report
from ..models import DailySalesSummary
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class DailySalesReport(EnsuresDailySales, Report):
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

    def query(self):
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
