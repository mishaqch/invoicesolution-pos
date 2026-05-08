"""Tenant-scoped manager + queryset.

Pattern: explicit + system-check (per the approved Phase 0 plan §5).

The manager exposes `for_tenant(tenant_id)` but does not auto-filter. A Django
system check (apps/tenants/checks.py) verifies every tenant-scoped model uses
this manager as its default. Tests then verify each viewset filters correctly.

Why not auto-filter from a thread-local: management commands, fixtures,
migrations, and cross-tenant audit/reconciliation jobs would all need a
context-manager to bypass; thread-local + Celery is a known footgun. Explicit
filtering is what CLAUDE.md ("every queryset MUST filter by tenant_id")
already mandates.
"""

from __future__ import annotations

from django.db import models


class TenantScopedQuerySet(models.QuerySet):
    def for_tenant(self, tenant_id):
        """Filter to a single tenant. The canonical entry point."""
        return self.filter(tenant_id=tenant_id)


class TenantScopedManager(models.Manager.from_queryset(TenantScopedQuerySet)):
    pass
