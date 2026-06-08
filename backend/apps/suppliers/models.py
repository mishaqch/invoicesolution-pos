"""Supplier records (pharmacy / wholesale procurement).

A Supplier is a tenant-scoped party we buy stock from. Goods receipts
(apps.purchases) reference a supplier and create ProductBatch rows, so a
pharmacist can trace any batch back to who it came from. Soft-deleted
(deleted_at) per the audit-don't-delete invariant.
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


class Supplier(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    # Tax identifiers — useful for pharma distributors who issue tax invoices.
    ntn = models.CharField(max_length=20, blank=True, null=True)
    strn = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "suppliers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]

    def __str__(self) -> str:
        return self.name
