"""Customer top-N — biggest spenders over a period."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Sum

from apps.sales.models import Invoice

from ..aggregates import COUNTED_STATUSES
from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    limit: int = 50


@register
class CustomerTopNReport(Report):
    name = "customer_top_n"
    Filters = _Filters
    columns = (
        Column("rank", "Rank", "int", "right"),
        Column("name", "Customer"),
        Column("phone", "Phone"),
        Column("invoice_count", "Visits", "int", "right"),
        Column("total_spent", "Total spent", "money", "right"),
        Column("avg_ticket", "Avg ticket", "money", "right"),
    )

    def query(self):
        qs = (
            Invoice.objects.for_tenant(self.tenant_id)
            .filter(status__in=COUNTED_STATUSES, customer__isnull=False)
        )
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(invoice_date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(invoice_date__lte=self.filters.date_to)
        rows = (
            qs.values("customer_id", "customer__name", "customer__phone")
            .annotate(
                invoice_count=Count("id"),
                total_spent=Sum("grand_total"),
            )
            .order_by("-total_spent")[: self.filters.limit]
        )
        for idx, r in enumerate(rows, start=1):
            count = r["invoice_count"] or 0
            total = r["total_spent"] or Decimal("0")
            yield {
                "rank": idx,
                "name": r["customer__name"],
                "phone": r["customer__phone"] or "",
                "invoice_count": count,
                "total_spent": total,
                "avg_ticket": (total / count) if count else Decimal("0"),
            }
