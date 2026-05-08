"""In-app notifications. DATABASE_SCHEMA.md §11."""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


SEVERITIES = (
    ("info", "Info"),
    ("warning", "Warning"),
    ("danger", "Danger"),
    ("success", "Success"),
)


class Notification(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, blank=True, null=True,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    message = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITIES, default="info")
    data = models.JSONField(blank=True, null=True)
    read_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(
                fields=["user"], name="idx_notifications_user_unread",
                condition=models.Q(read_at__isnull=True),
            ),
        ]
