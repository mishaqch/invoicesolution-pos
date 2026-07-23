"""Payment adapter base class.

Each method (cash, card, easypaisa, jazzcash, raast, bank_transfer,
store_credit, cheque) is a subclass that:
  - declares its `method` enum value (matches Payment.payment_method).
  - implements validate_input(data) → dict (returns the cleaned data).
  - implements record_payment(*, invoice, amount, data, user) → Payment.

Refunds (Phase 6 wires the full UX):
  - cash / store_credit / cheque can be processed locally.
  - card / wallet / bank_transfer are recorded only — the actual reversal
    happens on the bank's terminal or in the wallet app, and the cashier
    enters the reference.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.sales.models import Invoice, Payment


class PaymentValidationError(serializers.ValidationError):
    pass


class PaymentAdapter(ABC):
    method: str

    @abstractmethod
    def validate_input(self, data: dict) -> dict:
        """Coerce + validate the method-specific fields. Return cleaned dict."""

    @abstractmethod
    def record_payment(
        self,
        *,
        invoice: Invoice,
        amount: Decimal,
        data: dict,
        user=None,
        require_details: bool = True,
    ) -> Payment:
        """Persist the Payment row + any side effects (ledger, drawer, etc.).

        require_details: when False, method-specific proof fields that are
        normally mandatory (e.g. card_last4 / card_auth_code) become optional.
        Set False for back-office MANUAL invoicing, where the operator keys an
        invoice after the fact and may not have the physical card slip — the
        POS terminal keeps the strict default (the cashier has the slip in hand).
        """

    # Optional refund hook — Phase 6 returns will use this.
    def can_refund_locally(self) -> bool:
        return False

    def refund(
        self,
        original: Payment,
        *,
        amount: Decimal,
        user=None,
    ) -> Payment:
        """Default: refund just records a negative-amount payment row that
        references the original. Subclasses can override for side effects
        (e.g. store_credit refund increments the customer's credit)."""
        return Payment.objects.create(
            tenant_id=original.tenant_id,
            invoice=original.invoice,
            customer=original.customer,
            payment_method=original.payment_method,
            amount=Decimal("-1") * Decimal(amount),
            status="refunded",
            refund_of=original,
            received_by=user,
        )


# ---------------------------------------------------------------------------
# Helpers used by several adapters
# ---------------------------------------------------------------------------


def _digits(value: Any, *, length: int | None = None, field: str) -> str:
    if value is None or value == "":
        if length is None:
            return ""
        raise PaymentValidationError({field: "Required."})
    s = str(value).strip()
    if not s.isdigit():
        raise PaymentValidationError({field: "Must contain digits only."})
    if length is not None and len(s) != length:
        raise PaymentValidationError({field: f"Must be exactly {length} digits."})
    return s
