"""Tenant + TenantMembership models.

Field-by-field mapping to DATABASE_SCHEMA.md §1. Deviations from the raw SQL
are noted inline.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.uuid7 import uuid7

# ---------------------------------------------------------------------------
# Enums (kept as module-level tuples so we can also reference them in CHECK
# constraints via migrations; choices=… on the field gives us form validation
# for free.)
# ---------------------------------------------------------------------------

BUSINESS_TYPES = (
    ("sole_proprietor", "Sole Proprietor"),
    ("partnership", "Partnership"),
    ("private_ltd", "Private Limited"),
    ("public_ltd", "Public Limited"),
    ("aop", "Association of Persons"),
)

PROVINCES = (
    ("PUNJAB", "Punjab"),
    ("SINDH", "Sindh"),
    ("KP", "Khyber Pakhtunkhwa"),
    ("BALOCHISTAN", "Balochistan"),
    ("ICT", "Islamabad Capital Territory"),
    ("GB", "Gilgit-Baltistan"),
    ("AJK", "Azad Jammu & Kashmir"),
)

SUBSCRIPTION_PLANS = (
    ("starter", "Starter"),
    ("pro", "Pro"),
    ("enterprise", "Enterprise"),
)

SUBSCRIPTION_STATUSES = (
    ("trial", "Trial"),
    ("active", "Active"),
    ("past_due", "Past due"),
    ("suspended", "Suspended"),
    ("cancelled", "Cancelled"),
)

ROLES = (
    ("owner", "Owner"),
    ("manager", "Manager"),
    ("cashier", "Cashier"),
    ("accountant", "Accountant"),
    ("auditor", "Auditor"),
)


class Tenant(models.Model):
    """The business that has subscribed to our POS.

    Tenant has no `tenant` FK (it IS the tenant) so it inherits from plain
    Model + manual timestamp fields rather than TenantScopedModel.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    business_name = models.CharField(max_length=255)
    ntn = models.CharField(max_length=20, unique=True)
    strn = models.CharField(max_length=20, blank=True, null=True)
    cnic_owner = models.CharField(max_length=15, blank=True, null=True)

    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES)
    fbr_business_natures = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
    )
    fbr_sector = models.CharField(max_length=50, blank=True, null=True)
    province = models.CharField(max_length=20, choices=PROVINCES)

    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    logo_url = models.TextField(blank=True, null=True)

    subscription_plan = models.CharField(
        max_length=50, choices=SUBSCRIPTION_PLANS, default="starter"
    )
    subscription_status = models.CharField(
        max_length=20, choices=SUBSCRIPTION_STATUSES, default="trial"
    )
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    next_billing_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants"

    def __str__(self) -> str:
        return self.business_name


class TenantMembership(models.Model):
    """Which user belongs to which tenant, in what role."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=30, choices=ROLES)

    # Schema says UUID[]; empty list means "all branches".
    branch_ids = ArrayField(models.UUIDField(), default=list, blank=True)

    is_active = models.BooleanField(default=True)
    custom_permissions = models.JSONField(default=dict, blank=True)

    invited_at = models.DateTimeField(blank=True, null=True)
    joined_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                name="uniq_tenant_user_membership",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_memberships_user"),
            models.Index(
                fields=["tenant"],
                name="idx_memberships_tenant_active",
                condition=models.Q(is_active=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} → {self.tenant_id} ({self.role})"
