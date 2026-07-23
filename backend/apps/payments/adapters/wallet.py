"""Wallet adapters — EasyPaisa, JazzCash, Raast.

All three follow the same shape: cashier reads a transaction reference off
the customer's app and types it into the POS, optionally with the customer's
phone. Validation is mostly cosmetic (we trust the cashier).

V1.5: replace these with real merchant-API integrations (see
INTEGRATIONS.md §2.3.2 / §2.4 / §2.5).
"""

from __future__ import annotations

from decimal import Decimal

from apps.sales.models import Invoice, Payment

from .base import PaymentAdapter, PaymentValidationError


class _WalletAdapterBase(PaymentAdapter):
    method: str
    provider: str

    def validate_input(self, data: dict) -> dict:
        tx_id = (data.get("wallet_transaction_id") or "").strip()
        if not tx_id:
            raise PaymentValidationError({
                "wallet_transaction_id": "Required — see customer's app for the reference.",
            })
        phone = (data.get("wallet_phone") or "").strip() or None
        return {
            "wallet_transaction_id": tx_id,
            "wallet_phone": phone,
            "wallet_provider": self.provider,
        }

    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
        require_details: bool = True,  # unused (wallet tx id always required)
    ) -> Payment:
        clean = self.validate_input(data)
        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=invoice.customer,
            payment_method=self.method,
            amount=Decimal(amount),
            wallet_transaction_id=clean["wallet_transaction_id"],
            wallet_phone=clean["wallet_phone"],
            wallet_provider=clean["wallet_provider"],
            received_by=user,
            status="completed",
        )


class EasyPaisaAdapter(_WalletAdapterBase):
    method = "easypaisa"
    provider = "easypaisa"


class JazzCashAdapter(_WalletAdapterBase):
    method = "jazzcash"
    provider = "jazzcash"


class RaastAdapter(_WalletAdapterBase):
    """Raast — same wire format but uses raast_* columns instead of wallet_*."""

    method = "raast"
    provider = "raast"

    def validate_input(self, data: dict) -> dict:
        tx_id = (data.get("raast_transaction_id") or data.get("wallet_transaction_id") or "").strip()
        if not tx_id:
            raise PaymentValidationError({
                "raast_transaction_id": "Required — reference from the customer's banking app.",
            })
        return {
            "raast_transaction_id": tx_id,
            "raast_iban": (data.get("raast_iban") or "").strip() or None,
        }

    def record_payment(
        self, *, invoice: Invoice, amount: Decimal, data: dict, user=None,
        require_details: bool = True,  # unused (wallet tx id always required)
    ) -> Payment:
        clean = self.validate_input(data)
        return Payment.objects.create(
            tenant_id=invoice.tenant_id,
            invoice=invoice,
            customer=invoice.customer,
            payment_method="raast",
            amount=Decimal(amount),
            raast_transaction_id=clean["raast_transaction_id"],
            raast_iban=clean["raast_iban"],
            received_by=user,
            status="completed",
        )
