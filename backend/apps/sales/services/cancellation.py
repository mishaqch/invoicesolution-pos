"""Cancel an invoice.

Phase 2 ships the basic admin "cancel sale" action: reverse stock, mark
the invoice cancelled, append audit. The 72-hour edit-window check and the
10% monthly cancel-budget consumption land in Phase 4 (FBR).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.inventory.services.movements import record_movement

from ..models import Invoice


@transaction.atomic
def cancel_invoice(
    invoice: Invoice, *, reason: str, user=None, request=None,
) -> Invoice:
    # PRAL DI manual v1.6 §"Conditions for Invoice Cancellation":
    # only FBR-accepted invoices are eligible for amendment.
    # `can_cancel_invoice` encodes the full matrix (FBR-accepted,
    # within 72h, no edited items, not annexure-C-linked).
    from apps.fbr.rules import can_cancel_invoice
    allowed, why = can_cancel_invoice(invoice)
    if not allowed:
        raise ValidationError({"status": why})

    # Reverse the sale movements (positive return movement per line).
    for item in invoice.items.select_related("product", "variant"):
        if item.is_cancelled:
            continue
        record_movement(
            tenant_id=invoice.tenant_id,
            product=item.product,
            variant=item.variant,
            branch=invoice.branch,
            warehouse=invoice.warehouse,
            movement_type="return",
            quantity=item.quantity,  # positive: returning to stock
            unit_cost=item.cost_price,
            reference_type="invoice",
            reference_id=invoice.id,
            performed_by=user,
            reason=f"Cancellation of {invoice.local_invoice_number}",
        )
        item.is_cancelled = True
        item.cancelled_at = timezone.now()
        item.save(update_fields=["is_cancelled", "cancelled_at"])

    invoice.status = "cancelled"
    invoice.reason = "manual_cancel"
    invoice.reason_notes = reason
    invoice.save(update_fields=["status", "reason", "reason_notes", "updated_at"])

    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="invoice", entity_id=invoice.id, action="cancel",
        after={"reason": reason}, request=request,
    )
    return invoice


@transaction.atomic
def delete_draft_invoice(invoice: Invoice, *, user=None, request=None) -> str:
    """SOFT-delete an UNSUBMITTED draft invoice (never accepted by FBR).

    Allowed only when the invoice has no fbr_invoice_number and is in a
    pre-validation state (pending_sync / failed) — see rules.can_delete_draft.

    Why soft, not hard: a draft the operator clicked "Validate" on already has
    an append-only fbr_submissions lint row (UPDATE/DELETE revoked at the DB
    level for 6-year compliance), so its FK can't be nulled and a hard delete is
    impossible. Soft-delete (set deleted_at) hides it from every tenant-facing
    list while preserving the audit + submission history — the platform's
    "audit, don't delete" invariant.

    Stock: stock_movements are append-only too, so we append a reversing
    `return` movement per line to put the stock back (honest sale → reversal
    history). Returns the local_invoice_number.
    """
    from apps.fbr.rules import can_delete_draft

    allowed, why = can_delete_draft(invoice)
    if not allowed:
        raise ValidationError({"status": why})

    number = invoice.local_invoice_number

    # Put stock back via reversing movements (only for lines that moved stock).
    for item in invoice.items.select_related("product", "variant"):
        if item.is_cancelled or item.product_id is None:
            continue
        record_movement(
            tenant_id=invoice.tenant_id,
            product=item.product,
            variant=item.variant,
            branch=invoice.branch,
            warehouse=invoice.warehouse,
            movement_type="return",
            quantity=item.quantity,  # positive: returning to stock
            unit_cost=item.cost_price,
            reference_type="invoice",
            reference_id=invoice.id,
            performed_by=user,
            reason=f"Draft invoice {number} deleted before FBR submission",
        )

    invoice.deleted_at = timezone.now()
    invoice.status = "cancelled"
    invoice.save(update_fields=["deleted_at", "status", "updated_at"])

    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="invoice", entity_id=invoice.id, action="delete_draft",
        before={"local_invoice_number": number, "grand_total": str(invoice.grand_total)},
        request=request,
    )
    return number


@transaction.atomic
def cancel_sale_item(
    invoice: Invoice, sale_item_id: str, *, reason: str, user=None, request=None,
):
    """Cancel ONE item on an invoice (PRAL-style per-item cancel).

    Returns the SaleItem and flips invoice.status to partially_cancelled
    if other items remain valid, or cancelled if every item is now cancelled.

    Stock for the cancelled line is reversed via a `return` movement so
    the books stay in sync. Per CLAUDE.md, audit-don't-delete: the
    sale_item row is kept with is_cancelled=true, never deleted.
    """
    item = invoice.items.select_related("product", "variant").get(pk=sale_item_id)
    if item.is_cancelled:
        raise ValidationError({"item": "Item already cancelled."})
    if item.is_edited:
        raise ValidationError({"item": "Cannot cancel an edited item."})

    record_movement(
        tenant_id=invoice.tenant_id,
        product=item.product,
        variant=item.variant,
        branch=invoice.branch,
        warehouse=invoice.warehouse,
        movement_type="return",
        quantity=item.quantity,
        unit_cost=item.cost_price,
        reference_type="invoice",
        reference_id=invoice.id,
        performed_by=user,
        reason=f"Item cancellation on {invoice.local_invoice_number}",
    )
    item.is_cancelled = True
    item.cancelled_at = timezone.now()
    item.save(update_fields=["is_cancelled", "cancelled_at"])

    # Recompute invoice status from item flags.
    items = list(invoice.items.all())
    if all(it.is_cancelled for it in items):
        invoice.status = "cancelled"
    else:
        invoice.status = "partially_cancelled"
    invoice.reason_notes = reason
    invoice.save(update_fields=["status", "reason_notes", "updated_at"])

    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="sale_item", entity_id=item.id, action="cancel",
        after={"reason": reason, "invoice_id": str(invoice.id)},
        request=request,
    )
    return item
