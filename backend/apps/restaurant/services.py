"""Restaurant order services — kitchen firing + floor/table aggregation.

Orders ARE held sales.Invoices (no separate model). These helpers operate on
that invoice's restaurant fields. KOT printing happens on the terminal; the
server only records that an order was fired (status + timestamp) and exposes
the kitchen queue + floor map.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.sales.models import Invoice


@transaction.atomic
def send_to_kitchen(invoice: Invoice, *, user=None, request=None) -> Invoice:
    """Mark a held order as fired to the kitchen and flag its unsent lines.

    Idempotent-friendly: re-firing only flips newly-added (unsent) lines and
    bumps the timestamp, so a 'course 2' fire doesn't re-fire course 1.
    """
    before = {"order_status": invoice.order_status, "kitchen_sent_at": str(invoice.kitchen_sent_at)}

    # Flag any not-yet-fired lines as sent (the terminal prints only these on a
    # KOT; the flag is what makes re-firing incremental).
    invoice.items.filter(sent_to_kitchen=False, is_cancelled=False).update(sent_to_kitchen=True)

    invoice.order_status = "sent_to_kitchen"
    invoice.kitchen_sent_at = timezone.now()
    invoice.save(update_fields=["order_status", "kitchen_sent_at", "updated_at"])

    audit.log(
        tenant_id=invoice.tenant_id, user=user, entity_type="invoice",
        entity_id=invoice.id, action="send_to_kitchen",
        before=before,
        after={"order_status": invoice.order_status, "kitchen_sent_at": str(invoice.kitchen_sent_at)},
        request=request,
    )
    return invoice


@transaction.atomic
def set_order_status(invoice: Invoice, status: str, *, user=None, request=None) -> Invoice:
    """Advance the kitchen status (sent_to_kitchen → ready → served)."""
    before = invoice.order_status
    invoice.order_status = status
    invoice.save(update_fields=["order_status", "updated_at"])
    audit.log(
        tenant_id=invoice.tenant_id, user=user, entity_type="invoice",
        entity_id=invoice.id, action="order_status",
        before={"order_status": before}, after={"order_status": status},
        request=request,
    )
    return invoice


def open_orders_qs(tenant_id, *, branch_id=None):
    """Held (open) restaurant orders for a tenant, optionally one branch."""
    qs = (
        Invoice.objects.for_tenant(tenant_id)
        .filter(is_held=True, deleted_at__isnull=True)
        .filter(order_type__isnull=False)  # restaurant orders only
        .select_related("table", "customer")
        .prefetch_related("items")
        .order_by("kitchen_sent_at", "-id")
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs
