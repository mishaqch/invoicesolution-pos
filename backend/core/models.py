"""Abstract base models reused across apps.

Every model in this codebase ultimately inherits from one of these. The
hierarchy:

    TimestampedModel       — created_at / updated_at on every table.
        TenantScopedModel  — adds tenant FK + TenantScopedManager as default.

The Tenant model itself inherits from TimestampedModel directly (it IS the
tenant, so it can't be tenant-scoped). The User model is also untenanted,
since one user can belong to multiple tenants via TenantMembership.
"""

from __future__ import annotations

from django.db import models

from apps.tenants.managers import TenantScopedManager


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScopedModel(TimestampedModel):
    """Base for any model that lives inside a tenant boundary.

    Composite indexes on subclasses must lead with `tenant` per CLAUDE.md.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
    )

    objects = TenantScopedManager()

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["tenant"])]
