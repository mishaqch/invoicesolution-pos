"""Inventory Celery tasks.

Phase 1 ships:
- daily low-stock digest (`inventory.low_stock_digest`)
- weekly stock-valuation report (`inventory.stock_valuation_report`)
  cached in Redis 7d, emailed Mondays 06:00 PKT
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from celery import shared_task
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
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


# ---------------------------------------------------------------------------
# Weekly stock valuation
# ---------------------------------------------------------------------------


def _valuation_cache_key(tenant_id) -> str:
    return f"stock_valuation:{tenant_id}"


def compute_stock_valuation(tenant: Tenant) -> dict:
    """Sum quantity × cost_price per branch for one tenant.

    Returns a dict shaped for the cache + email body:
        {
          "tenant_id": str,
          "computed_at": ISO-8601,
          "total_value": Decimal-as-str,
          "by_branch": [
            {"branch_id": str, "branch_name": str,
             "total_value": str, "sku_count": int}
          ],
        }
    """
    from django.utils import timezone

    rows = (
        StockLevel.objects
        .filter(tenant=tenant, quantity__gt=0)
        .annotate(
            line_value=ExpressionWrapper(
                F("quantity") * F("product__cost_price"),
                output_field=DecimalField(max_digits=18, decimal_places=4),
            ),
        )
        .values("branch_id", "branch__name")
        .annotate(
            total_value=Sum("line_value"),
            sku_count=Sum(Value(1, output_field=DecimalField(max_digits=8, decimal_places=0))),
        )
        .order_by("branch__name")
    )

    by_branch = []
    grand = Decimal("0")
    for r in rows:
        v = r["total_value"] or Decimal("0")
        grand += v
        by_branch.append({
            "branch_id": str(r["branch_id"]),
            "branch_name": r["branch__name"],
            "total_value": str(v.quantize(Decimal("0.01"))),
            "sku_count": int(r["sku_count"] or 0),
        })

    return {
        "tenant_id": str(tenant.id),
        "computed_at": timezone.now().isoformat(),
        "total_value": str(grand.quantize(Decimal("0.01"))),
        "by_branch": by_branch,
    }


def get_cached_stock_valuation(tenant: Tenant) -> dict | None:
    """Read the cached report. Returns None on miss; admin can call
    `stock_valuation_report.delay(tenant_id)` to repopulate."""
    raw = cache.get(_valuation_cache_key(tenant.id))
    return json.loads(raw) if raw else None


@shared_task(name="inventory.stock_valuation_report")
def stock_valuation_report(tenant_id: str | None = None):
    """Weekly stock valuation for one or all tenants.

    - When `tenant_id` is provided, runs for that tenant only (used as
      an on-demand admin trigger).
    - Otherwise loops every tenant — wired to Celery beat at 06:00 PKT
      every Monday.

    The result is cached in Redis under `stock_valuation:<tenant>` for
    7 days so the admin dashboard can read it without recomputing on
    every page load. The owner / accountant role members also receive
    an email summary.
    """
    qs = Tenant.objects.all()
    if tenant_id:
        qs = qs.filter(pk=tenant_id)

    sent = 0
    for tenant in qs:
        try:
            report = compute_stock_valuation(tenant)
        except Exception:
            logger.exception(
                "stock_valuation: compute failed for tenant=%s", tenant.id,
            )
            continue

        cache.set(
            _valuation_cache_key(tenant.id),
            json.dumps(report),
            timeout=60 * 60 * 24 * 7,   # 7 days
        )

        recipients = list(
            TenantMembership.objects
            .filter(tenant=tenant, is_active=True, role__in=("owner", "accountant"))
            .values_list("user__email", flat=True)
        )
        if not recipients:
            logger.info(
                "stock_valuation: tenant=%s — no recipients; cached only",
                tenant.id,
            )
            continue

        send_mail(
            subject=f"[{tenant.business_name}] Weekly stock valuation — "
                    f"Rs. {report['total_value']}",
            message=_valuation_body(tenant, report),
            from_email=None,    # uses DEFAULT_FROM_EMAIL
            recipient_list=recipients,
            fail_silently=True,
        )
        sent += 1
    return {"tenants_processed": qs.count(), "emails_sent": sent}


def _valuation_body(tenant: Tenant, report: dict) -> str:
    lines = [
        f"Weekly stock valuation for {tenant.business_name}.",
        "",
        f"Total value across all branches: Rs. {report['total_value']}",
        "",
        "Per-branch breakdown:",
    ]
    for b in report["by_branch"]:
        lines.append(
            f"  • {b['branch_name']}: Rs. {b['total_value']}  "
            f"({b['sku_count']} SKUs in stock)"
        )
    if not report["by_branch"]:
        lines.append("  (no stock on hand)")
    lines.extend([
        "",
        "This report is also cached in the admin dashboard for 7 days.",
        "Sign in to the admin web app to see the live numbers.",
    ])
    return "\n".join(lines)
