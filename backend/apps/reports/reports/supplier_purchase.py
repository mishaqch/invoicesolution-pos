"""Supplier purchase summary.

The 'purchases' and 'suppliers' apps are scaffolded but not implemented
yet (they ship in a later phase). This report is registered so the
admin UI surfaces it in the catalog; the query returns an empty result
set with a one-row 'no data' explanation. Once the underlying app
ships, swap the query for the real one without touching consumers.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class SupplierPurchaseReport(Report):
    name = "supplier_purchase"
    Filters = _Filters
    columns = (
        Column("supplier_name", "Supplier"),
        Column("purchase_count", "Purchases", "int", "right"),
        Column("total_purchased", "Total Rs", "money", "right"),
        Column("outstanding", "Outstanding Rs", "money", "right"),
    )

    def query(self):
        # Purchases module not implemented yet. Returning an empty
        # iterable so the report renders cleanly (no rows + a totals
        # block with zeros). The UI shows a "No data — purchases module
        # not yet enabled" empty state when row_count == 0.
        return iter(())
