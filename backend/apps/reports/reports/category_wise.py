"""Category-wise sales rollup."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import F, Sum

from apps.catalog.models import Category

from ..base import BaseFilters, ChartSpec, Column, Report
from ..models import ProductVelocity
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class CategoryWiseReport(Report):
    name = "category_wise"
    Filters = _Filters
    columns = (
        Column("name", "Category"),
        Column("quantity", "Qty", "decimal", "right"),
        Column("revenue", "Revenue", "money", "right"),
        Column("cogs", "COGS", "money", "right"),
        Column("margin", "Margin", "money", "right"),
    )
    chart_spec = ChartSpec(type="bar", x_key="name", y_keys=("revenue",))

    def query(self):
        qs = ProductVelocity.objects.for_tenant(self.tenant_id)
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(date__lte=self.filters.date_to)

        rows = (
            qs.annotate(category_id=F("product__category_id"))
            .values("category_id")
            .annotate(
                quantity=Sum("quantity"),
                revenue=Sum("net_revenue"),   # tax-exclusive, so margin is honest
                cogs=Sum("cogs"),
            )
            .order_by("-revenue")
        )
        cat_ids = [r["category_id"] for r in rows if r["category_id"]]
        cat_map = {
            c.id: c.name for c in Category.objects.filter(id__in=cat_ids).only("id", "name")
        }
        for r in rows:
            revenue = r["revenue"] or Decimal("0")
            cogs = r["cogs"] or Decimal("0")
            yield {
                "name": cat_map.get(r["category_id"], "(uncategorized)"),
                "quantity": r["quantity"] or Decimal("0"),
                "revenue": revenue,
                "cogs": cogs,
                "margin": revenue - cogs,
            }
