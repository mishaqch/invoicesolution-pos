"""Profit & loss — revenue, COGS, gross margin per period.

Uses ProductVelocity which snapshots cost_price at sale-time, so margin
is accurate even if product cost has changed since.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from ..base import BaseFilters, ChartSpec, Column, Report
from ..models import ProductVelocity
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class ProfitLossReport(Report):
    name = "profit_loss"
    Filters = _Filters
    columns = (
        Column("date", "Date", "date"),
        Column("revenue", "Revenue", "money", "right"),
        Column("cogs", "COGS", "money", "right"),
        Column("margin", "Gross margin", "money", "right"),
        Column("margin_pct", "Margin %", "percent", "right"),
    )
    chart_spec = ChartSpec(type="line", x_key="date", y_keys=("revenue", "margin"))

    def query(self):
        qs = ProductVelocity.objects.for_tenant(self.tenant_id)
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(date__lte=self.filters.date_to)
        rows = (
            qs.values("date")
            .annotate(revenue=Sum("revenue"), cogs=Sum("cogs"))
            .order_by("date")
        )
        for r in rows:
            revenue = r["revenue"] or Decimal("0")
            cogs = r["cogs"] or Decimal("0")
            margin = revenue - cogs
            margin_pct = (margin / revenue * 100) if revenue else Decimal("0")
            yield {
                "date": r["date"],
                "revenue": revenue,
                "cogs": cogs,
                "margin": margin,
                "margin_pct": margin_pct,
            }

    def totals(self, rows):
        if not rows:
            return {}
        revenue = sum((r["revenue"] for r in rows), Decimal("0"))
        cogs = sum((r["cogs"] for r in rows), Decimal("0"))
        margin = revenue - cogs
        return {
            "revenue": revenue,
            "cogs": cogs,
            "margin": margin,
            "margin_pct": (margin / revenue * 100) if revenue else Decimal("0"),
        }
