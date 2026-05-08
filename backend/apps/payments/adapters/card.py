"""Card adapters (credit + debit)."""

from __future__ import annotations

from decimal import Decimal

from apps.sales.models import Invoice, Payment

from .base import PaymentAdapter, PaymentValidationError, _digits


class _CardAdapterBase(PaymentAdapter):
    method: str  # set by subclass

    def validate_input(self, data: dict) -> dict:
        return {
            "card_last4": _digits(data.get("card_last4"), length=4, field="card_last4"),
            "card_auth_code": _digits(
                data.get("card_auth_code"), length=6, field="card_auth_code",
            ),
            # RRN optional per INTEGRATIONS.md §2.2. Format varies by acquirer
            # (some 12-digit numeric, some 23-char alphanumeric). Accept any
            # non-empty trimmed string.
            "card_rrn": (
                str(data["card_rrn"]).strip() or None if data.get("card_rrn") else None
            ),
            "card_terminal_id": (data.get("card_terminal_id") or "").strip() or None,
        }

    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
    ) -> Payment:
        clean = self.validate_input(data)
        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=invoice.customer,
            payment_method=self.method,
            amount=Decimal(amount),
            card_last4=clean["card_last4"],
            card_auth_code=clean["card_auth_code"],
            card_rrn=clean["card_rrn"],
            card_terminal_id=clean["card_terminal_id"],
            received_by=user,
            status="completed",
        )


class CardCreditAdapter(_CardAdapterBase):
    method = "card_credit"


class CardDebitAdapter(_CardAdapterBase):
    method = "card_debit"
