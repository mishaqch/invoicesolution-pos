"""Audit log — append-only.

Defense in depth, same pattern as stock_movements:
  1. DB-level REVOKE (migration 0002)
  2. Django pre_save / pre_delete signal guard (apps/audit/signals.py)

Per CLAUDE.md the legal retention is 6 years. Phase 8 will add the archive
policy; Phase 2 makes the table immutable so nothing's lost in the meantime.
"""

from __future__ import annotations

from django.db import models

from core.uuid7 import uuid7


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    # tenant_id is nullable so we keep an audit trail even after tenant
    # deletion (legal: a deleted tenant's audit log is still our record).
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
    )

    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField(blank=True, null=True)
    action = models.CharField(max_length=50)

    before_data = models.JSONField(blank=True, null=True)
    after_data = models.JSONField(blank=True, null=True)
    changes = models.JSONField(blank=True, null=True)

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(
                fields=["tenant", "-created_at"], name="idx_audit_tenant_date",
            ),
            models.Index(
                fields=["entity_type", "entity_id"], name="idx_audit_entity",
            ),
            models.Index(fields=["user"], name="idx_audit_user"),
        ]
