"""SyncLog — server-side trace of every POS-originated write.

Per DATABASE_SCHEMA.md §10. The UNIQUE constraint on `client_uuid` is the
idempotency mechanism: a duplicate POST race fails with IntegrityError,
which the API handler turns into a "duplicate" response that replays the
prior outcome.

Statuses:
  received   — row inserted, processing in progress.
  processed  — handler succeeded, entity_id pinned.
  failed     — 4xx validation failure or unrecoverable error. Surfaces to
               admin via notifications.
  duplicate  — same client_uuid seen again; payload was a no-op.

Note: unlike audit_log this table IS mutable (status transitions, retry
attempts). The audit story for sync is captured by audit_log entries that
checkout/holds/etc. write — sync_log is operational metadata.
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


SYNC_LOG_STATUSES = (
    ("received", "Received"),
    ("processed", "Processed"),
    ("failed", "Failed"),
    ("duplicate", "Duplicate"),
)


class SyncLog(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    terminal = models.ForeignKey(
        "tenants.Terminal", on_delete=models.PROTECT, related_name="sync_logs",
    )
    client_uuid = models.UUIDField(unique=True)
    entity_type = models.CharField(max_length=30)
    entity_id = models.UUIDField(blank=True, null=True)
    action = models.CharField(max_length=20)

    payload = models.JSONField()

    status = models.CharField(max_length=20, choices=SYNC_LOG_STATUSES, default="received")
    error_message = models.TextField(blank=True, null=True)

    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "sync_log"
        indexes = [
            models.Index(
                fields=["terminal", "-received_at"], name="idx_sync_log_terminal",
            ),
            models.Index(
                fields=["tenant"], name="idx_sync_log_failed",
                condition=models.Q(status="failed"),
            ),
        ]

    def mark_processed(self, entity_id):
        from django.utils import timezone
        self.entity_id = entity_id
        self.status = "processed"
        self.processed_at = timezone.now()
        self.save(update_fields=["entity_id", "status", "processed_at", "updated_at"])

    def mark_failed(self, message: str):
        from django.utils import timezone
        self.status = "failed"
        self.error_message = message
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "processed_at", "updated_at"])
