"""Stock aging — bucket on-hand inventory by age of last 'received' movement.

Heuristic: for each (product, branch), find the most recent 'received' or
'opening_balance' StockMovement; bucket the days-since-received into
0-30 / 31-60 / 61-90 / 91+. Items with stock but no received movement
fall into 'unknown'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from apps.inventory.models import StockLevel, StockMovement

from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


def _bucket(age_days: int | None) -> str:
    if age_days is None:
        return "unknown"
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    return "91+"


@register
class StockAgingReport(Report):
    name = "stock_aging"
    Filters = _Filters
    columns = (
        Column("sku", "SKU"),
        Column("name", "Product"),
        Column("branch_name", "Branch"),
        Column("quantity", "On hand", "decimal", "right"),
        Column("last_received_at", "Last received", "datetime"),
        Column("age_days", "Age (days)", "int", "right"),
        Column("bucket", "Bucket"),
    )

    def query(self):
        stock = (
            StockLevel.objects.for_tenant(self.tenant_id)
            .filter(quantity__gt=0)
            .select_related("product", "branch")
        )
        if self.filters.branch_id:
            stock = stock.filter(branch_id=self.filters.branch_id)

        # Most-recent received per (product, branch).
        last_received = (
            StockMovement.objects.for_tenant(self.tenant_id)
            # Real inbound movement types (there is NO "received" type — that
            # was a StockTransfer STATUS, not a movement_type, so the report was
            # dead for every purchase/transfer-replenished item).
            .filter(movement_type__in=["purchase", "transfer_in", "adjustment_in", "opening_balance"])
            .values("product_id", "branch_id")
            .annotate(last=Max("created_at"))
        )
        last_map = {
            (r["product_id"], r["branch_id"]): r["last"] for r in last_received
        }

        now = timezone.now()
        for s in stock:
            last = last_map.get((s.product_id, s.branch_id))
            age_days = (now - last).days if last else None
            yield {
                "sku": s.product.sku,
                "name": s.product.name,
                "branch_name": s.branch.name,
                "quantity": s.quantity,
                "last_received_at": last,
                "age_days": age_days,
                "bucket": _bucket(age_days),
            }
