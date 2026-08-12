"""Returns analysis — return rate, refund total, breakdown by reason + route."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Sum

from apps.returns.models import Return

from ..base import BaseFilters, ChartSpec, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class ReturnsAnalysisReport(Report):
    name = "returns_analysis"
    Filters = _Filters
    columns = (
        Column("reason", "Reason"),
        Column("fbr_route", "FBR route"),
        Column("count", "Count", "int", "right"),
        Column("total_refund", "Refund Rs", "money", "right"),
    )
    chart_spec = ChartSpec(type="bar", x_key="reason", y_keys=("count",))

    def query(self):
        # Only COMPLETED returns count — a cancelled return still carries a
        # refund_amount and would inflate the totals + count.
        qs = Return.objects.for_tenant(self.tenant_id).filter(status="completed")
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(return_date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(return_date__lte=self.filters.date_to)
        rows = (
            qs.values("reason", "fbr_route")
            .annotate(count=Count("id"), total_refund=Sum("refund_amount"))
            .order_by("reason", "fbr_route")
        )
        for r in rows:
            yield {
                "reason": r["reason"] or "unspecified",
                "fbr_route": r["fbr_route"] or "n/a",   # non-fiscal returns have none
                "count": r["count"],
                "total_refund": r["total_refund"] or Decimal("0"),
            }
