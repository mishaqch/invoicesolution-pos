"""Helpers for writing audit entries.

The only sanctioned way to write an AuditLog row from application code.
Centralizes IP/UA capture and change diffing.
"""

from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .models import AuditLog


def log(
    *,
    tenant_id: UUID | str | None,
    user=None,
    entity_type: str,
    entity_id: UUID | str | None = None,
    action: str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    request=None,
) -> AuditLog:
    changes = _compute_changes(before, after) if before is not None and after is not None else None
    ip = ua = None
    if request is not None:
        ip = _client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT") if hasattr(request, "META") else None
    return AuditLog.objects.create(
        tenant_id=tenant_id,
        user=user,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_data=dict(before) if before is not None else None,
        after_data=dict(after) if after is not None else None,
        changes=changes,
        ip_address=ip,
        user_agent=ua,
    )


def _compute_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict:
    diff: dict[str, list] = {}
    keys = set(before) | set(after)
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b != a:
            diff[k] = [b, a]
    return diff


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
