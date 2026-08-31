"""Top movers + slow movers — sister reports.

Top movers: products by revenue desc, top N.
Slow movers: products with stock>0 sold below threshold qty over the
range. We use ProductVelocity for sold-qty + StockLevel for current
inventory; stale-but-stocked items surface here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from apps.catalog.models import Product
from apps.inventory.models import StockLevel

from ..aggregates.ensure import EnsuresProductVelocity
from ..base import BaseFilters, Column, Report
from ..models import ProductVelocity
from ..registry import register


@dataclass
class _MoversFilters(BaseFilters):
    limit: int = 20
    # Slow movers = in-stock items that sold at-or-below this qty over the range.
    # Default 5 (not 0) so it means "low velocity", not only "never sold".
    min_sold_qty: str = "5"


@register
class TopMoversReport(EnsuresProductVelocity, Report):
    name = "top_movers"
    Filters = _MoversFilters
    columns = (
        Column("rank", "Rank", "int", "right"),
        Column("sku", "SKU"),
        Column("name", "Product"),
        Column("quantity", "Qty sold", "decimal", "right"),
        Column("revenue", "Revenue", "money", "right"),
    )

    def query(self):
        qs = ProductVelocity.objects.for_tenant(self.tenant_id)
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(date__lte=self.filters.date_to)
        rows = (
            qs.values("product_id")
            .annotate(quantity=Sum("quantity"), revenue=Sum("net_revenue"))
            .order_by("-revenue")[: self.filters.limit]
        )
        product_ids = [r["product_id"] for r in rows]
        product_map = {
            p.id: p for p in Product.objects.for_tenant(self.tenant_id)
            .filter(id__in=product_ids).only("id", "name", "sku")
        }
        for idx, r in enumerate(rows, start=1):
            p = product_map.get(r["product_id"])
            yield {
                "rank": idx,
                "sku": p.sku if p else "",
                "name": p.name if p else "(deleted)",
                "quantity": r["quantity"] or Decimal("0"),
                "revenue": r["revenue"] or Decimal("0"),
            }


@register
class SlowMoversReport(EnsuresProductVelocity, Report):
    name = "slow_movers"
    Filters = _MoversFilters
    columns = (
        Column("sku", "SKU"),
        Column("name", "Product"),
        Column("quantity", "Qty sold", "decimal", "right"),
        Column("stock_on_hand", "On hand", "decimal", "right"),
    )

    def query(self):
        # Sold-qty per product across the range.
        sold = ProductVelocity.objects.for_tenant(self.tenant_id)
        if self.filters.branch_id:
            sold = sold.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            sold = sold.filter(date__gte=self.filters.date_from)
        if self.filters.date_to:
            sold = sold.filter(date__lte=self.filters.date_to)
        sold_map = {
            r["product_id"]: r["q"] or Decimal("0")
            for r in sold.values("product_id").annotate(q=Sum("quantity"))
        }
        # Current inventory.
        stock_qs = StockLevel.objects.for_tenant(self.tenant_id).filter(quantity__gt=0)
        if self.filters.branch_id:
            stock_qs = stock_qs.filter(branch_id=self.filters.branch_id)
        threshold = Decimal(self.filters.min_sold_qty)
        candidates = stock_qs.values("product_id").annotate(stock=Sum("quantity"))
        results = []
        for c in candidates:
            sold_qty = sold_map.get(c["product_id"], Decimal("0"))
            if sold_qty <= threshold:
                results.append({
                    "product_id": c["product_id"],
                    "stock_on_hand": c["stock"],
                    "sold_qty": sold_qty,
                })
        results.sort(key=lambda r: r["sold_qty"])
        results = results[: self.filters.limit]
        product_ids = [r["product_id"] for r in results]
        product_map = {
            p.id: p for p in Product.objects.filter(id__in=product_ids).only("id", "name", "sku")
        }
        for r in results:
            p = product_map.get(r["product_id"])
            yield {
                "sku": p.sku if p else "",
                "name": p.name if p else "(deleted)",
                "quantity": r["sold_qty"],
                "stock_on_hand": r["stock_on_hand"],
            }
