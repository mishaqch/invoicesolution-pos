"""Payment method breakdown — totals + count per method, with a donut chart."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Sum

from apps.sales.models import Payment

from ..base import BaseFilters, ChartSpec, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class PaymentBreakdownReport(Report):
    name = "payment_breakdown"
    Filters = _Filters
    columns = (
        Column("payment_method", "Method"),
        Column("count", "Count", "int", "right"),
        Column("total", "Total", "money", "right"),
    )
    chart_spec = ChartSpec(type="donut", x_key="payment_method", y_keys=("total",))

    def query(self):
        qs = Payment.objects.for_tenant(self.tenant_id).filter(status="completed")
        if self.filters.branch_id:
            qs = qs.filter(invoice__branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(invoice__invoice_date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(invoice__invoice_date__lte=self.filters.date_to)
        rows = (
            qs.values("payment_method")
            .annotate(count=Count("id"), total=Sum("amount"))
            .order_by("-total")
        )
        for r in rows:
            yield {
                "payment_method": r["payment_method"],
                "count": r["count"],
                "total": r["total"] or Decimal("0"),
            }
