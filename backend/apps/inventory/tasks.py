"""Inventory Celery tasks.

Phase 1 ships the daily low-stock digest only.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from celery import shared_task
from django.core.mail import send_mail
from django.db.models import F, Value
from django.db.models.functions import Coalesce

from apps.tenants.models import Branch, Tenant, TenantMembership

from .models import StockLevel

logger = logging.getLogger(__name__)


@shared_task(name="inventory.low_stock_digest")
def low_stock_digest():
    """For each tenant, group below-threshold stock per branch and email.

    Threshold rule: stock_level.quantity <= COALESCE(stock_level.reorder_level,
    products.reorder_level, 0). The partial index `idx_stock_low` (migration
    inventory.0002) accelerates this query.

    Recipients per branch: tenant owners + managers whose branch_ids include
    that branch (or whose branch_ids is empty == all branches).

    Idempotent for the day: each tenant gets at most one email per branch
    per calendar day (we'd persist a sent-record in Phase 7 reports; for now
    Celery beat scheduling at 7am once daily provides the same effect).
    """
    today = date.today()
    sent = 0
    for tenant in Tenant.objects.all():
        levels = (
            StockLevel.objects.filter(tenant_id=tenant.id)
            .annotate(
                threshold=Coalesce(F("reorder_level"), F("product__reorder_level"), Value(0)),
            )
            .filter(quantity__lte=F("threshold"))
            .select_related("product", "branch")
        )
        per_branch: dict = defaultdict(list)
        for lvl in levels:
            per_branch[lvl.branch].append(lvl)

        for branch, items in per_branch.items():
            recipients = _recipients_for_branch(tenant, branch)
            if not recipients:
                logger.info(
                    "low_stock_digest: tenant=%s branch=%s — no recipients", tenant.id, branch.id
                )
                continue
            send_mail(
                subject=f"[{tenant.business_name}] Low stock — {branch.name} ({today})",
                message=_format_body(items),
                from_email=None,
                recipient_list=recipients,
                fail_silently=True,
            )
            sent += 1
    return {"emails_sent": sent}


def _recipients_for_branch(tenant: Tenant, branch: Branch) -> list[str]:
    memberships = TenantMembership.objects.filter(
        tenant=tenant,
        is_active=True,
        role__in=("owner", "manager"),
    ).select_related("user")
    out: list[str] = []
    for m in memberships:
        if m.role == "owner" or not m.branch_ids or branch.id in m.branch_ids:
            out.append(m.user.email)
    return out


def _format_body(items) -> str:
    lines = ["The following products are at or below their reorder level:\n"]
    for lvl in items:
        lines.append(
            f"  • {lvl.product.name} (SKU {lvl.product.sku}) — "
            f"qty {lvl.quantity} (reorder at {lvl.threshold})"
        )
    lines.append("\nLog into the admin to review and reorder.")
    return "\n".join(lines)
