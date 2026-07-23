"""Bank transfer adapter."""

from __future__ import annotations

from decimal import Decimal

from apps.sales.models import Invoice, Payment

from .base import PaymentAdapter, PaymentValidationError


class BankTransferAdapter(PaymentAdapter):
    method = "bank_transfer"

    def validate_input(self, data: dict) -> dict:
        bank = (data.get("bank_name") or "").strip()
        if not bank:
            raise PaymentValidationError({"bank_name": "Required."})
        ref = (data.get("bank_reference") or "").strip()
        if not ref:
            raise PaymentValidationError({"bank_reference": "Required."})
        last4 = (data.get("bank_account_last4") or "").strip() or None
        return {
            "bank_name": bank,
            "bank_account_last4": last4,
            "bank_reference": ref,
        }

    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
        require_details: bool = True,  # unused (bank fields always required)
    ) -> Payment:
        clean = self.validate_input(data)
        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=invoice.customer,
            payment_method="bank_transfer",
            amount=Decimal(amount),
            bank_name=clean["bank_name"],
            bank_account_last4=clean["bank_account_last4"],
            bank_reference=clean["bank_reference"],
            received_by=user,
            status="completed",
        )
