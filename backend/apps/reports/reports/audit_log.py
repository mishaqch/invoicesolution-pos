"""Audit log report — append-only history of every meaningful change.

AuditLog is technically a global table (tenant_id is nullable for the
deleted-tenant case) — but reports always filter by the current tenant.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.audit.models import AuditLog

from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    entity_type: str | None = None
    user_id: str | None = None


@register
class AuditLogReport(Report):
    name = "audit_log"
    Filters = _Filters
    columns = (
        Column("created_at", "When", "datetime"),
        Column("user_email", "User"),
        Column("entity_type", "Entity"),
        Column("entity_id", "ID"),
        Column("action", "Action"),
        Column("ip_address", "IP"),
    )

    def query(self):
        qs = AuditLog.objects.filter(tenant_id=self.tenant_id).select_related("user")
        if self.filters.entity_type:
            qs = qs.filter(entity_type=self.filters.entity_type)
        if self.filters.user_id:
            qs = qs.filter(user_id=self.filters.user_id)
        if self.filters.date_from:
            qs = qs.filter(created_at__date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(created_at__date__lte=self.filters.date_to)
        for r in qs.order_by("-created_at")[:5000]:
            yield {
                "created_at": r.created_at,
                "user_email": r.user.email if r.user else "(system)",
                "entity_type": r.entity_type,
                "entity_id": str(r.entity_id) if r.entity_id else "",
                "action": r.action,
                "ip_address": r.ip_address or "",
            }
