"""Item-wise sales — quantity, revenue, COGS per product.

Source: product_velocity. Adds product name + SKU via select_related.
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
    category_id: str | None = None


@register
class ItemWiseReport(Report):
    name = "item_wise"
    Filters = _Filters
    columns = (
        Column("sku", "SKU"),
        Column("name", "Product"),
        Column("quantity", "Qty", "decimal", "right"),
        Column("revenue", "Revenue", "money", "right"),
        Column("cogs", "COGS", "money", "right"),
        Column("margin", "Margin", "money", "right"),
    )
    chart_spec = ChartSpec(type="bar", x_key="name", y_keys=("revenue",))

    def query(self):
        qs = ProductVelocity.objects.for_tenant(self.tenant_id).select_related("product")
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(date__lte=self.filters.date_to)
        if self.filters.category_id:
            qs = qs.filter(product__category_id=self.filters.category_id)

        rows = (
            qs.values("product_id")
            .annotate(
                quantity=Sum("quantity"),
                revenue=Sum("revenue"),
                cogs=Sum("cogs"),
            )
            .order_by("-revenue")
        )
        # Re-fetch product display fields in one query.
        from apps.catalog.models import Product
        product_ids = [r["product_id"] for r in rows]
        product_map = {
            p.id: p for p in Product.objects.filter(id__in=product_ids).only("id", "name", "sku")
        }
        for r in rows:
            p = product_map.get(r["product_id"])
            revenue = r["revenue"] or Decimal("0")
            cogs = r["cogs"] or Decimal("0")
            yield {
                "sku": p.sku if p else "",
                "name": p.name if p else "(deleted)",
                "quantity": r["quantity"] or Decimal("0"),
                "revenue": revenue,
                "cogs": cogs,
                "margin": revenue - cogs,
            }
