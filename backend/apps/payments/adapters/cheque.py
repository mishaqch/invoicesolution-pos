"""Cheque adapter — records as 'pending' until manually cleared/bounced."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.sales.models import Invoice, Payment

from .base import PaymentAdapter, PaymentValidationError


class ChequeAdapter(PaymentAdapter):
    method = "cheque"

    def validate_input(self, data: dict) -> dict:
        number = (data.get("cheque_number") or "").strip()
        if not number:
            raise PaymentValidationError({"cheque_number": "Required."})
        bank = (data.get("bank_name") or "").strip()
        if not bank:
            raise PaymentValidationError({"bank_name": "Required."})
        date_raw = data.get("cheque_date")
        if not date_raw:
            raise PaymentValidationError({"cheque_date": "Required."})
        try:
            cheque_date = dt.date.fromisoformat(str(date_raw))
        except (TypeError, ValueError):
            raise PaymentValidationError({"cheque_date": "Use YYYY-MM-DD."})
        return {
            "cheque_number": number,
            "bank_name": bank,
            "cheque_date": cheque_date,
        }

    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
    ) -> Payment:
        clean = self.validate_input(data)
        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=invoice.customer,
            payment_method="cheque",
            amount=Decimal(amount),
            cheque_number=clean["cheque_number"],
            bank_name=clean["bank_name"],
            cheque_date=clean["cheque_date"],
            cheque_status="pending",
            received_by=user,
            # Status is "completed" from a sale-flow perspective even though
            # the cheque hasn't cleared. That's tracked separately on
            # cheque_status — see services.mark_cheque_cleared / _bounced.
            status="completed",
        )
