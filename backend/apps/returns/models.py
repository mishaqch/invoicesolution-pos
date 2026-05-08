"""Returns / refunds — DATABASE_SCHEMA.md §8.

Lifecycle:
  - process_return creates the Return + ReturnItems atomically.
  - The FBR roundtrip happens inside the same transaction; a failure
    rolls everything back.
  - Stock movements + customer ledger entries fire as part of the
    transaction so the books never diverge.
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


REASON_CHOICES = (
    ("damaged", "Damaged"),
    ("wrong_item", "Wrong item"),
    ("customer_changed_mind", "Customer changed mind"),
    ("expired", "Expired"),
    ("other", "Other"),
)

REFUND_METHOD_CHOICES = (
    ("cash", "Cash"),
    ("store_credit", "Store credit"),
    ("card_reversal", "Card reversal"),
    ("wallet_reversal", "Wallet reversal"),
    ("bank_transfer", "Bank transfer"),
)

STATUS_CHOICES = (
    ("pending", "Pending"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
)

# Phase 6 addition — which path the FBR submission took.
FBR_ROUTE_CHOICES = (
    ("amend", "Amend (within 72h)"),
    ("credit_note", "Credit note (outside 72h)"),
)


class Return(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT)
    terminal = models.ForeignKey("tenants.Terminal", on_delete=models.PROTECT)
    cashier = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="returns",
    )
    original_invoice = models.ForeignKey(
        "sales.Invoice", on_delete=models.PROTECT, related_name="returns",
    )

    return_number = models.CharField(max_length=40)
    fbr_credit_note_number = models.CharField(max_length=40, blank=True, null=True)
    return_date = models.DateField()

    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    reason_notes = models.TextField(blank=True, default="")

    refund_method = models.CharField(max_length=30, choices=REFUND_METHOD_CHOICES)
    refund_amount = models.DecimalField(max_digits=14, decimal_places=4)

    fbr_route = models.CharField(
        max_length=20, choices=FBR_ROUTE_CHOICES, blank=True, null=True,
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="completed")

    # Idempotency key — POS-generated. Mirrors invoice.client_uuid.
    client_uuid = models.UUIDField(unique=True)

    class Meta:
        db_table = "returns"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "return_number"],
                name="uniq_return_tenant_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "-return_date"],
                name="idx_returns_tenant_date",
            ),
            models.Index(fields=["original_invoice"], name="idx_returns_orig"),
        ]

    def __str__(self) -> str:
        return self.return_number


class ReturnItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    return_ref = models.ForeignKey(
        Return, on_delete=models.CASCADE, related_name="items",
    )
    original_sale_item = models.ForeignKey(
        "sales.SaleItem", on_delete=models.PROTECT, related_name="returned_items",
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, blank=True, null=True,
    )

    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=4)

    restocked = models.BooleanField(default=True)
    # Movement type written on the inventory side (sale, return, damage, expiry).
    # Recorded for traceability.
    movement_type = models.CharField(max_length=30, blank=True, default="")

    class Meta:
        db_table = "return_items"
