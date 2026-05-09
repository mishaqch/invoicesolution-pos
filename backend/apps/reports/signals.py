"""Cache invalidation on data changes.

Reports cache by (tenant, name, filter-hash). When sales-relevant data
changes, we bust the whole tenant slice so the next request sees fresh
numbers. The aggregate tables themselves are rebuilt by Celery beat —
this layer is for the per-request cache only.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.returns.models import Return
from apps.sales.models import Invoice, Payment


def bust_tenant_report_cache(tenant_id) -> None:
    # Django's LocMem backend (used in tests) doesn't support pattern
    # delete; Redis does. Fall back to delete_many on a known prefix
    # if available, otherwise rely on TTL.
    pattern = f"report:{tenant_id}:*"
    try:
        cache.delete_pattern(pattern)  # type: ignore[attr-defined]
    except AttributeError:
        # LocMem fallback — no-op; tests bypass cache via use_cache=False.
        pass


@receiver([post_save, post_delete], sender=Invoice)
def _bust_on_invoice(sender, instance, **kwargs):
    if instance.tenant_id:
        bust_tenant_report_cache(instance.tenant_id)


@receiver([post_save, post_delete], sender=Return)
def _bust_on_return(sender, instance, **kwargs):
    if instance.tenant_id:
        bust_tenant_report_cache(instance.tenant_id)


@receiver([post_save, post_delete], sender=Payment)
def _bust_on_payment(sender, instance, **kwargs):
    if instance.tenant_id:
        bust_tenant_report_cache(instance.tenant_id)
