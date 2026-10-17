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
        # The materialized aggregate is keyed (tenant, branch, date) — it has
        # no terminal dimension, so it cannot answer "just Terminal 2". When a
        # terminal is selected, compute the same shape live from invoices
        # instead. Slightly slower, but correct; without a terminal the fast
        # aggregate path is unchanged.
        if getattr(self.filters, "terminal_id", None):
            yield from self._query_live()
            return

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

    def _query_live(self):
        """Per-day totals straight from invoices, scoped to one terminal."""
        from django.db.models import Count, Sum

        from apps.sales.models import Invoice

        qs = Invoice.objects.filter(
            tenant_id=self.tenant_id, is_held=False, deleted_at__isnull=True,
        ).exclude(status="cancelled")
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        qs = qs.filter(terminal_id=self.filters.terminal_id)
        if self.filters.date_from:
            qs = qs.filter(invoice_date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(invoice_date__lte=self.filters.date_to)

        rows = (
            qs.values("invoice_date", "branch__name")
            .annotate(
                invoice_count=Count("id"),
                gross=Sum("grand_total"),
                tax=Sum("tax_total"),
            )
            .order_by("invoice_date", "branch__name")
        )
        for r in rows:
            gross = r["gross"] or Decimal("0")
            tax = r["tax"] or Decimal("0")
            yield {
                "date": r["invoice_date"],
                "branch_name": r["branch__name"],
                "invoice_count": r["invoice_count"],
                "gross": gross,
                "tax": tax,
                "net": gross - tax,
                # Returns are not terminal-scoped in V1; shown as 0 rather
                # than mis-attributing a branch refund to one till.
                "refund_count": 0,
                "refund_amount": Decimal("0"),
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
