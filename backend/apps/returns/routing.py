"""FBR routing for returns.

Within 72h AND no items edited → 'amend' (consumes 10% budget,
calls cancelinvoice or item-cancel on PRAL).

Otherwise → 'credit_note' (separate invoice with invoice_type='credit_note',
references the original via reference_invoice_id; doesn't consume the
cancel budget).
"""

from __future__ import annotations

from typing import Literal

from apps.fbr.rules import can_cancel_invoice
from apps.sales.models import Invoice


FbrRoute = Literal["amend", "credit_note"]


def determine_fbr_route(invoice: Invoice) -> FbrRoute:
    allowed_to_amend, _ = can_cancel_invoice(invoice)
    return "amend" if allowed_to_amend else "credit_note"
