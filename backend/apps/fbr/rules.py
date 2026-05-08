"""Edit / cancel constraint matrix from INTEGRATIONS.md §1.11.

Pure functions: no DB writes, no external calls. Each returns
(allowed: bool, reason: str | None). Called by both server-side services
(authoritative) and the admin UI (for disabling buttons).
"""

from __future__ import annotations

from django.utils import timezone

from apps.sales.models import Invoice, SaleItem


def _past_deadline(invoice: Invoice) -> bool:
    return (
        invoice.edit_deadline_at is not None
        and timezone.now() > invoice.edit_deadline_at
    )


def can_edit_item(invoice: Invoice, item: SaleItem) -> tuple[bool, str | None]:
    if invoice.status == "finalized":
        return False, "Invoice is already in submitted return"
    if _past_deadline(invoice):
        return False, "72-hour edit window has passed"
    if item.is_cancelled:
        return False, "Item is already cancelled"
    if item.edit_count >= 1:
        return False, "Item has already been edited (max 1 edit allowed)"
    if invoice.is_annexure_c_linked:
        return False, "Invoices linked to Annexure-C cannot be edited"
    return True, None


def can_cancel_item(invoice: Invoice, item: SaleItem) -> tuple[bool, str | None]:
    if invoice.status == "finalized":
        return False, "Invoice is already in submitted return"
    if _past_deadline(invoice):
        return False, "72-hour cancel window has passed"
    if item.is_cancelled:
        return False, "Item is already cancelled"
    if item.is_edited:
        return False, "Cannot cancel an edited item"
    if invoice.is_annexure_c_linked:
        return False, "Invoices linked to Annexure-C cannot have items cancelled"
    return True, None


def can_cancel_invoice(invoice: Invoice) -> tuple[bool, str | None]:
    """Cancel the whole invoice. Budget consumption is checked separately."""
    if invoice.status == "finalized":
        return False, "Invoice is already finalized"
    if invoice.status == "cancelled":
        return False, "Invoice is already cancelled"
    if _past_deadline(invoice):
        return False, "72-hour cancel window has passed"
    for item in invoice.items.all():
        if item.is_edited:
            return False, "Cannot cancel: at least one item has been edited"
    if invoice.is_annexure_c_linked:
        return False, "Invoices linked to Annexure-C cannot be cancelled"
    return True, None
