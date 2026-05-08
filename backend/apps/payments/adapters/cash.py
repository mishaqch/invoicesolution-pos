"""Cash adapter."""

from __future__ import annotations

from decimal import Decimal

from apps.sales.models import Invoice, Payment

from .base import PaymentAdapter


class CashAdapter(PaymentAdapter):
    method = "cash"

    def validate_input(self, data: dict) -> dict:
        return {}  # nothing method-specific beyond amount

    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
    ) -> Payment:
        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=invoice.customer,
            payment_method="cash",
            amount=Decimal(amount),
            received_by=user,
            status="completed",
        )

    def can_refund_locally(self) -> bool:
        return True
