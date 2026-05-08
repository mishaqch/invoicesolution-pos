"""Customer + customer_groups + customer_ledger.

Per DATABASE_SCHEMA.md §6. Phase 2 lands the structure; the ledger is
written by sales/services/checkout for registered customers (cash walk-ins
skip the ledger, per the Phase 2 plan).
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


REGISTRATION_TYPES = (
    ("registered", "Registered"),
    ("unregistered", "Unregistered"),
)


class CustomerGroup(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100)
    default_discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )

    class Meta:
        db_table = "customer_groups"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uniq_customer_group_name"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Customer(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    group = models.ForeignKey(
        CustomerGroup, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="customers",
    )
    customer_code = models.CharField(max_length=20, blank=True, null=True)

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    cnic = models.CharField(max_length=15, blank=True, null=True)
    ntn = models.CharField(max_length=20, blank=True, null=True)

    registration_type = models.CharField(
        max_length=20, choices=REGISTRATION_TYPES, default="unregistered"
    )

    # 'PUNJAB' | 'SINDH' | etc — choices kept loose at the DB so we don't
    # cross-couple to the tenants module's enum here. Validated at the
    # serializer / form layer.
    province = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, default="")
    date_of_birth = models.DateField(blank=True, null=True)

    credit_limit = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    current_balance = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
    )  # positive = customer owes us
    store_credit = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    loyalty_points = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")

    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "customers"
        indexes = [
            models.Index(
                fields=["tenant"], name="idx_customers_tenant",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["tenant", "phone"], name="idx_customers_phone",
                condition=models.Q(phone__isnull=False),
            ),
            # gin FTS index added via RunSQL in 0002 migration
        ]

    def __str__(self) -> str:
        return self.name


LEDGER_TX_TYPES = (
    ("sale", "Sale"),
    ("payment", "Payment"),
    ("return", "Return"),
    ("adjustment", "Adjustment"),
    ("opening", "Opening"),
)


class CustomerLedger(TenantScopedModel):
    """Append-only ledger of every customer balance change.

    Running_balance is computed at write time via select_for_update on the
    customer row, never recomputed lazily — consistency over performance.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="ledger_entries"
    )

    transaction_type = models.CharField(max_length=30, choices=LEDGER_TX_TYPES)
    reference_type = models.CharField(max_length=30, blank=True, null=True)
    reference_id = models.UUIDField(blank=True, null=True)

    debit = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    running_balance = models.DecimalField(max_digits=14, decimal_places=4)

    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
    )

    class Meta:
        db_table = "customer_ledger"
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="idx_ledger_customer_date",
            ),
        ]
