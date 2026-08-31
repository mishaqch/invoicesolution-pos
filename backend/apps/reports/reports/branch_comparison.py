"""Branch comparison — gross + count + refunds + avg ticket per branch."""

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
class BranchComparisonReport(EnsuresDailySales, Report):
    name = "branch_comparison"
    Filters = _Filters
    columns = (
        Column("branch_name", "Branch"),
        Column("invoice_count", "Invoices", "int", "right"),
        Column("gross", "Gross", "money", "right"),
        Column("net", "Net", "money", "right"),
        Column("refund_count", "Refunds", "int", "right"),
        Column("refund_amount", "Refund Rs", "money", "right"),
        Column("avg_ticket", "Avg ticket", "money", "right"),
    )
    chart_spec = ChartSpec(type="bar", x_key="branch_name", y_keys=("gross",))

    def query(self):
        qs = DailySalesSummary.objects.for_tenant(self.tenant_id).select_related("branch")
        if self.filters.date_from:
            qs = qs.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(date__lte=self.filters.date_to)
        rows = (
            qs.values("branch_id", "branch__name")
            .annotate(
                invoice_count=Sum("invoice_count"),
                gross=Sum("gross"),
                net=Sum("net"),
                refund_count=Sum("refund_count"),
                refund_amount=Sum("refund_amount"),
            )
            .order_by("-gross")
        )
        for r in rows:
            count = r["invoice_count"] or 0
            gross = r["gross"] or Decimal("0")
            yield {
                "branch_name": r["branch__name"],
                "invoice_count": count,
                "gross": gross,
                "net": r["net"] or Decimal("0"),
                "refund_count": r["refund_count"] or 0,
                "refund_amount": r["refund_amount"] or Decimal("0"),
                "avg_ticket": (gross / count) if count else Decimal("0"),
            }
