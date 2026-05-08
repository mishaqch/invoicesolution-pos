"""Append-only guard for AuditLog (early-warning; DB grants are the truth)."""

from __future__ import annotations

from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from .models import AuditLog


class AuditLogImmutableError(PermissionError):
    pass


@receiver(pre_save, sender=AuditLog)
def block_audit_update(sender, instance: AuditLog, **kwargs):
    if instance.pk is not None and AuditLog.objects.filter(pk=instance.pk).exists():
        raise AuditLogImmutableError(
            "audit_log is append-only. Insert a new row instead of updating."
        )


@receiver(pre_delete, sender=AuditLog)
def block_audit_delete(sender, instance: AuditLog, **kwargs):
    raise AuditLogImmutableError("audit_log is append-only. Delete is forbidden.")
