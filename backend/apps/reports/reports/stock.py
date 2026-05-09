"""Stock report — current quantity by branch, with reorder flags."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.inventory.models import StockLevel

from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    only_low: bool = False
    only_in_stock: bool = False


@register
class StockReport(Report):
    name = "stock"
    Filters = _Filters
    columns = (
        Column("sku", "SKU"),
        Column("name", "Product"),
        Column("branch_name", "Branch"),
        Column("quantity", "On hand", "decimal", "right"),
        Column("reserved_quantity", "Reserved", "decimal", "right"),
        Column("reorder_level", "Reorder at", "decimal", "right"),
        Column("status", "Status"),
    )

    def query(self):
        qs = (
            StockLevel.objects.for_tenant(self.tenant_id)
            .select_related("product", "branch")
        )
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.only_in_stock:
            qs = qs.filter(quantity__gt=0)
        for s in qs.order_by("branch__name", "product__name"):
            qty = s.quantity
            reorder = s.reorder_level or Decimal("0")
            if qty <= 0:
                status = "out_of_stock"
            elif reorder and qty <= reorder:
                status = "low"
            else:
                status = "ok"
            if self.filters.only_low and status == "ok":
                continue
            yield {
                "sku": s.product.sku,
                "name": s.product.name,
                "branch_name": s.branch.name,
                "quantity": qty,
                "reserved_quantity": s.reserved_quantity,
                "reorder_level": reorder,
                "status": status,
            }
