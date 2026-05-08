"""Hold + recall sales.

A held sale is just an invoice with `is_held=True` and no payments. Phase 2
keeps held sales server-side so the admin can audit them; the POS terminal
mirrors them in local SQLite for the cashier.
"""

from __future__ import annotations

from django.db import transaction

from apps.audit.services import log as audit_log

from ..models import Invoice


@transaction.atomic
def hold(invoice: Invoice, *, label: str, user=None, request=None) -> Invoice:
    invoice.is_held = True
    invoice.held_label = label[:50] if label else None
    invoice.save(update_fields=["is_held", "held_label", "updated_at"])
    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="invoice", entity_id=invoice.id, action="hold",
        after={"label": invoice.held_label}, request=request,
    )
    return invoice


@transaction.atomic
def recall(invoice: Invoice, *, user=None, request=None) -> Invoice:
    invoice.is_held = False
    invoice.held_label = None
    invoice.save(update_fields=["is_held", "held_label", "updated_at"])
    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="invoice", entity_id=invoice.id, action="recall",
        request=request,
    )
    return invoice
