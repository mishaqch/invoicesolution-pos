"""Store-credit adapter — debits the customer's store_credit balance."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.customers.models import Customer, CustomerLedger
from apps.sales.models import Invoice, Payment

from .base import PaymentAdapter, PaymentValidationError


class StoreCreditAdapter(PaymentAdapter):
    method = "store_credit"

    def validate_input(self, data: dict) -> dict:
        return {}  # method-specific data is implicit (the customer's balance)

    @transaction.atomic
    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
    ) -> Payment:
        if invoice.customer is None:
            raise PaymentValidationError({
                "customer": "Store credit requires a registered customer on the sale.",
            })
        amt = Decimal(amount)
        # Lock the customer row so concurrent attempts can't double-spend.
        locked = Customer.objects.select_for_update().get(pk=invoice.customer_id)
        if locked.store_credit < amt:
            raise PaymentValidationError({
                "amount": (
                    f"Insufficient store credit. Available: Rs {locked.store_credit}, "
                    f"requested: Rs {amt}."
                ),
            })
        locked.store_credit -= amt
        locked.save(update_fields=["store_credit", "updated_at"])

        # Ledger entry — we treat the spent credit as a credit applied
        # against the customer's balance.
        new_balance = locked.current_balance  # store_credit is separate from
                                              # current_balance; balance unchanged.
        CustomerLedger.objects.create(
            tenant_id=invoice.tenant_id,
            customer=locked,
            transaction_type="payment",
            reference_type="invoice",
            reference_id=invoice.id,
            debit=Decimal(0),
            credit=amt,
            running_balance=new_balance,
            notes=f"Store credit applied to {invoice.local_invoice_number}",
            created_by=user,
        )

        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=locked,
            payment_method="store_credit",
            amount=amt,
            received_by=user,
            status="completed",
        )

    def can_refund_locally(self) -> bool:
        return True

    @transaction.atomic
    def refund(
        self, original: Payment, *, amount: Decimal, user=None,
    ) -> Payment:
        # Refund means crediting the balance back.
        if original.customer_id is None:
            return super().refund(original, amount=amount, user=user)
        locked = Customer.objects.select_for_update().get(pk=original.customer_id)
        locked.store_credit += Decimal(amount)
        locked.save(update_fields=["store_credit", "updated_at"])
        return super().refund(original, amount=amount, user=user)
