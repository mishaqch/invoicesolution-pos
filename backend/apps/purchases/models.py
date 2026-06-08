"""Goods receipt (GRN) — the canonical way stock + batches enter inventory.

A GoodsReceipt records a delivery from a supplier into a branch. Each line names
a product, quantity, cost, and (for batch-tracked goods) a batch number +
expiry. Posting the receipt creates/updates ProductBatch rows and records
`purchase` stock movements via record_movement (the single sanctioned stock
mutation), so stock, batch quantities, and the audit ledger all stay in step.

A draft receipt can be edited; once posted it's immutable (it has moved stock).
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7

GRN_STATUSES = (
    ("draft", "Draft"),
    ("posted", "Posted"),
)


class GoodsReceipt(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    reference = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Supplier invoice / delivery-note number.",
    )
    received_date = models.DateField()
    status = models.CharField(max_length=10, choices=GRN_STATUSES, default="draft")
    notes = models.TextField(blank=True, null=True)

    posted_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="+",
    )

    class Meta:
        db_table = "goods_receipts"
        ordering = ["-received_date", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "supplier"]),
        ]

    def __str__(self) -> str:
        return f"GRN {self.reference or self.id} ({self.status})"


class GoodsReceiptItem(models.Model):
    """One product line on a goods receipt. Inherits the tenant of its GRN."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.CASCADE, related_name="items",
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="+",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True,
    )
    # Batch fields — used for batch-tracked products; ignored otherwise.
    batch_number = models.CharField(max_length=50, blank=True, null=True)
    manufactured_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)

    # Set on post: the batch this line created/topped-up (for traceability).
    batch = models.ForeignKey(
        "catalog.ProductBatch", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="+",
    )

    class Meta:
        db_table = "goods_receipt_items"
