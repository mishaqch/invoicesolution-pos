"""Inventory models — DATABASE_SCHEMA.md §4.

Critical invariant: stock_movements is APPEND-ONLY.

Two layers of enforcement:
  1. DB grants — REVOKE UPDATE, DELETE on the table from the application role
     (migration 0002 in this app). The truth.
  2. Django pre_save / pre_delete signals (apps/inventory/signals.py) raise
     PermissionError. This is the early-warning that catches ORM misuse in
     tests and in dev, where the dev role often has full grants.
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7

# ---------------------------------------------------------------------------
# Stock levels
# ---------------------------------------------------------------------------


class StockLevel(TenantScopedModel):
    """Current stock per (product, optional variant, branch)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="stock_levels",
    )
    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )

    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    reserved_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    reorder_level = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    last_counted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "stock_levels"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant", "branch"],
                name="uniq_stocklevel_product_variant_branch",
            ),
        ]
        indexes = [
            models.Index(fields=["branch"], name="idx_stock_branch"),
            # Partial index for low-stock added via RunSQL in migration.
        ]

    def __str__(self) -> str:
        return f"{self.product_id} @ {self.branch_id}: {self.quantity}"


# ---------------------------------------------------------------------------
# Stock movements — APPEND-ONLY (REVOKE in migration + signal guard)
# ---------------------------------------------------------------------------


MOVEMENT_TYPES = (
    ("sale", "Sale"),
    ("return", "Return"),
    ("purchase", "Purchase"),
    ("transfer_in", "Transfer in"),
    ("transfer_out", "Transfer out"),
    ("adjustment_in", "Adjustment in"),
    ("adjustment_out", "Adjustment out"),
    ("damage", "Damage"),
    ("expiry", "Expiry"),
    ("opening_balance", "Opening balance"),
)

REFERENCE_TYPES = (
    ("invoice", "Invoice"),
    ("return", "Return"),
    ("purchase_order", "Purchase order"),
    ("adjustment", "Adjustment"),
    ("transfer", "Transfer"),
    ("audit", "Audit"),
)


class StockMovement(TenantScopedModel):
    """Append-only ledger of every stock change."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    batch = models.ForeignKey(
        "catalog.ProductBatch",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT)

    movement_type = models.CharField(max_length=30, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)  # signed
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )

    reference_type = models.CharField(
        max_length=30, choices=REFERENCE_TYPES, blank=True, null=True
    )
    reference_id = models.UUIDField(blank=True, null=True)

    reason = models.TextField(blank=True, default="")
    performed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    # `updated_at` is inherited from TimestampedModel but stock movements should
    # never update — keep the column for compatibility with the abstract base
    # but the signal blocks any modification path.

    class Meta:
        db_table = "stock_movements"
        indexes = [
            models.Index(
                fields=["product", "-created_at"],
                name="idx_movements_product",
            ),
            models.Index(
                fields=["branch", "-created_at"],
                name="idx_movements_branch_date",
            ),
            models.Index(
                fields=["reference_type", "reference_id"],
                name="idx_movements_reference",
            ),
        ]


# ---------------------------------------------------------------------------
# Stock transfers
# ---------------------------------------------------------------------------


TRANSFER_STATUSES = (
    ("draft", "Draft"),
    ("dispatched", "Dispatched"),
    ("received", "Received"),
    ("cancelled", "Cancelled"),
)


class StockTransfer(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    transfer_number = models.CharField(max_length=20)

    from_branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.PROTECT,
        related_name="outbound_transfers",
    )
    to_branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.PROTECT,
        related_name="inbound_transfers",
    )

    status = models.CharField(max_length=20, choices=TRANSFER_STATUSES, default="draft")

    dispatched_at = models.DateTimeField(blank=True, null=True)
    dispatched_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )
    received_at = models.DateTimeField(blank=True, null=True)
    received_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "stock_transfers"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "transfer_number"],
                name="uniq_transfer_tenant_number",
            ),
        ]


class StockTransferItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, blank=True, null=True
    )
    quantity_dispatched = models.DecimalField(max_digits=14, decimal_places=4)
    quantity_received = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    variance = models.DecimalField(max_digits=14, decimal_places=4, blank=True, null=True)

    class Meta:
        db_table = "stock_transfer_items"


# ---------------------------------------------------------------------------
# Stock audits
# ---------------------------------------------------------------------------


AUDIT_STATUSES = (
    ("in_progress", "In progress"),
    ("finalized", "Finalized"),
    ("cancelled", "Cancelled"),
)


class StockAudit(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.PROTECT,
        related_name="audits",
    )
    audit_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=AUDIT_STATUSES, default="in_progress")
    started_at = models.DateTimeField()
    finalized_at = models.DateTimeField(blank=True, null=True)
    performed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "stock_audits"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "audit_number"],
                name="uniq_audit_tenant_number",
            ),
        ]


class StockAuditItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    audit = models.ForeignKey(
        StockAudit,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, blank=True, null=True
    )
    expected_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    variance = models.DecimalField(max_digits=14, decimal_places=4)
    variance_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "stock_audit_items"
