"""Notification helpers + threshold-based email alerts."""

from __future__ import annotations

import datetime as dt

from django.core.mail import send_mail
from django.utils import timezone

from apps.tenants.models import Tenant, TenantMembership

from .models import Notification

SYNC_FAIL_EMAIL_THRESHOLD = 5
SYNC_FAIL_EMAIL_WINDOW_MIN = 60


def notify(
    *,
    tenant_id,
    user=None,
    notification_type: str,
    title: str,
    message: str,
    severity: str = "info",
    data: dict | None = None,
) -> Notification:
    return Notification.objects.create(
        tenant_id=tenant_id,
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        severity=severity,
        data=data,
    )


def maybe_email_sync_failures(*, tenant: Tenant) -> None:
    """If 5+ sync rows failed in the last hour for this tenant, email the owner."""
    from apps.sync.models import SyncLog
    cutoff = timezone.now() - dt.timedelta(minutes=SYNC_FAIL_EMAIL_WINDOW_MIN)
    fails = SyncLog.objects.filter(
        tenant=tenant, status="failed", processed_at__gte=cutoff,
    ).count()
    if fails < SYNC_FAIL_EMAIL_THRESHOLD:
        return

    owners = (
        TenantMembership.objects.filter(tenant=tenant, role="owner", is_active=True)
        .select_related("user")
    )
    recipients = [m.user.email for m in owners if m.user.email]
    if not recipients:
        return

    send_mail(
        subject=f"[{tenant.business_name}] {fails} POS sync failures in the last hour",
        message=(
            f"Hi,\n\n{fails} sync attempts failed in the last hour for "
            f"{tenant.business_name}. Open the admin web Terminals page to "
            f"review and retry.\n"
        ),
        from_email=None,
        recipient_list=recipients,
        fail_silently=True,
    )
