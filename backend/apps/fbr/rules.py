"""Edit / cancel constraint matrix from INTEGRATIONS.md §1.11.

Pure functions: no DB writes, no external calls. Each returns
(allowed: bool, reason: str | None). Called by both server-side services
(authoritative) and the admin UI (for disabling buttons).
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.sales.models import Invoice, SaleItem


# PRAL DI manual v1.6 §"Conditions for Invoice Cancellation":
#   "The invoice date cannot be revised to a date earlier than 3 days
#    before the current system date."
# Manual is silent on the future side, but PRAL rejects future-dated
# invoices server-side. We enforce the same window on both ends so
# the tenant gets a fast, clear error before the JSON ever leaves us.
INVOICE_DATE_PAST_LIMIT_DAYS = 3


def can_use_invoice_date(invoice_date: dt.date) -> tuple[bool, str | None]:
    """Validate the `invoiceDate` field shape before submission.

    Returns (allowed, reason). Use at sale-create time and edit time.
    """
    today = timezone.localdate()
    if invoice_date > today:
        return False, "Invoice date cannot be in the future."
    delta_days = (today - invoice_date).days
    if delta_days > INVOICE_DATE_PAST_LIMIT_DAYS:
        return False, (
            f"Invoice date cannot be earlier than "
            f"{INVOICE_DATE_PAST_LIMIT_DAYS} days before today "
            f"(today is {today.isoformat()})."
        )
    return True, None


def _past_deadline(invoice: Invoice) -> bool:
    return (
        invoice.edit_deadline_at is not None
        and timezone.now() > invoice.edit_deadline_at
    )


# Per PRAL DI manual v1.6 §"Conditions for Invoice Cancellation":
#   "Only e-invoices received through DI Integration are eligible
#    for correction."
#
# In our state machine that means the invoice must have been ACCEPTED
# by PRAL — it has an fbr_invoice_number and is in one of the
# post-validation states below. Pre-validation states (pending_sync /
# submitted / failed) have nothing on PRAL's side to amend; the
# operator's only option in those states is Resubmit (or wait).
#
# `edited` is intentionally not listed here as an entry state for new
# edits — once an item is edited, the invoice transitions to
# `partially_edited` and further edits are constrained by per-item
# `edit_count` instead. Same for `cancelled` (terminal).
_FBR_ACCEPTED_STATES = frozenset({
    "valid",
    "partially_edited",
    "partially_cancelled",
    "partially_edited_and_cancelled",
})


def _is_fbr_accepted(invoice: Invoice) -> bool:
    """True only when PRAL has accepted the invoice and we have an
    FBR invoice number to anchor edits / cancels against."""
    return (
        invoice.status in _FBR_ACCEPTED_STATES
        and bool(invoice.fbr_invoice_number)
    )


def is_unsubmitted_draft(invoice: Invoice) -> bool:
    """True when the invoice has NEVER reached FBR — no fbr_invoice_number and
    still in a pre-validation state (pending_sync / failed). Such an invoice has
    nothing on PRAL's side, so the FBR amendment rules (72h window, 10% cancel
    budget, immutability) DON'T apply: it can be freely edited or hard-deleted
    like a draft. The moment it has an FBR number, the strict rules take over.
    """
    return (
        not invoice.fbr_invoice_number
        and invoice.status in ("pending_sync", "failed")
    )


def can_delete_draft(invoice: Invoice) -> tuple[bool, str | None]:
    """Whether this invoice may be hard-deleted as an unsubmitted draft."""
    if is_unsubmitted_draft(invoice):
        return True, None
    if invoice.fbr_invoice_number:
        return False, (
            "This invoice has an FBR number and cannot be deleted — "
            "cancel it through FBR instead (audit + 6-year retention)."
        )
    return False, f"Invoice in status '{invoice.status}' cannot be deleted."


def _not_yet_validated_reason(invoice: Invoice) -> str | None:
    """Friendly explanation for the not-yet-accepted case. Returns
    None when the invoice IS accepted (so the caller can short-circuit)."""
    if _is_fbr_accepted(invoice):
        return None
    # Map each pre-validation status to a concrete next action so the
    # operator knows what to do instead of "can't edit". These strings
    # surface verbatim in the UI's tooltip on a disabled button.
    status = invoice.status
    if status == "pending_sync":
        return (
            "Invoice is still queued for FBR submission. "
            "Wait for FBR to validate, then edit within 72 hours."
        )
    if status == "submitted":
        return (
            "Invoice is awaiting FBR validation. "
            "You can edit it once FBR returns an invoice number."
        )
    if status == "failed":
        return (
            "Invoice was rejected by FBR. Click Resubmit; once it's "
            "accepted you'll be able to edit it within 72 hours."
        )
    if status == "cancelled":
        return "Invoice is already cancelled."
    if status == "finalized":
        return "Invoice is already in a submitted return."
    if status == "edited":
        # This is a transitional state; treat as accepted by falling
        # through to None so the per-item edit_count check governs.
        return None
    return f"Invoice in '{status}' state cannot be amended."


def can_edit_item(invoice: Invoice, item: SaleItem) -> tuple[bool, str | None]:
    not_accepted = _not_yet_validated_reason(invoice)
    if not_accepted:
        return False, not_accepted
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
    not_accepted = _not_yet_validated_reason(invoice)
    if not_accepted:
        return False, not_accepted
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
    not_accepted = _not_yet_validated_reason(invoice)
    if not_accepted:
        return False, not_accepted
    if _past_deadline(invoice):
        return False, "72-hour cancel window has passed"
    for item in invoice.items.all():
        if item.is_edited:
            return False, "Cannot cancel: at least one item has been edited"
    if invoice.is_annexure_c_linked:
        return False, "Invoices linked to Annexure-C cannot be cancelled"
    return True, None
