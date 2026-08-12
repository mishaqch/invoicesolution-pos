"""Supplier purchase summary — spend per supplier from posted goods receipts.

Aggregates POSTED GoodsReceipts (a draft GRN hasn't moved stock/committed spend
yet) per supplier: number of receipts and total value = SUM(qty × cost). There is
no supplier AP/ledger model, so we do NOT report an "outstanding" balance — that
would imply payables tracking the system doesn't have.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce

from apps.purchases.models import GoodsReceipt, GoodsReceiptItem
from apps.suppliers.models import Supplier

from ..base import BaseFilters, ChartSpec, Column, Report
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
        Column("purchase_count", "Receipts", "int", "right"),
        Column("total_purchased", "Total Rs", "money", "right"),
    )
    chart_spec = ChartSpec(type="bar", x_key="supplier_name", y_keys=("total_purchased",))

    def query(self):
        # Receipt-count per supplier (posted GRNs only).
        grn = GoodsReceipt.objects.for_tenant(self.tenant_id).filter(status="posted")
        if self.filters.branch_id:
            grn = grn.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            grn = grn.filter(received_date__gte=self.filters.date_from)
        if self.filters.date_to:
            grn = grn.filter(received_date__lte=self.filters.date_to)
        counts = {
            r["supplier_id"]: r["n"]
            for r in grn.values("supplier_id").annotate(n=Count("id"))
        }

        # Total value per supplier = SUM(qty × cost) over the same posted GRNs.
        # GoodsReceiptItem isn't TenantScoped — scope through the receipt FK.
        items = GoodsReceiptItem.objects.filter(
            receipt__tenant_id=self.tenant_id,
            receipt__status="posted",
        )
        if self.filters.branch_id:
            items = items.filter(receipt__branch_id=self.filters.branch_id)
        if self.filters.date_from:
            items = items.filter(receipt__received_date__gte=self.filters.date_from)
        if self.filters.date_to:
            items = items.filter(receipt__received_date__lte=self.filters.date_to)
        totals = {
            r["receipt__supplier_id"]: r["total"]
            for r in items.values("receipt__supplier_id").annotate(
                total=Sum(
                    F("quantity") * Coalesce(F("cost_price"), Decimal("0")),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                ),
            )
        }

        supplier_ids = set(counts) | set(totals)
        if not supplier_ids:
            return
        sup_map = {
            s.id: s.name
            for s in Supplier.objects.for_tenant(self.tenant_id)
            .filter(id__in=supplier_ids).only("id", "name")
        }
        rows = [
            {
                "supplier_name": sup_map.get(sid, "(deleted)"),
                "purchase_count": counts.get(sid, 0),
                "total_purchased": totals.get(sid) or Decimal("0"),
            }
            for sid in supplier_ids
        ]
        rows.sort(key=lambda r: r["total_purchased"], reverse=True)
        yield from rows

    def totals(self, rows):
        return {
            "purchase_count": sum(r["purchase_count"] for r in rows),
            "total_purchased": sum((r["total_purchased"] for r in rows), Decimal("0")),
        }
