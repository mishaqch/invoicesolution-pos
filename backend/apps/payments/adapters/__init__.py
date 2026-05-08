"""Payment adapter registry."""

from __future__ import annotations

from .base import PaymentAdapter, PaymentValidationError
from .bank_transfer import BankTransferAdapter
from .card import CardCreditAdapter, CardDebitAdapter
from .cash import CashAdapter
from .cheque import ChequeAdapter
from .store_credit import StoreCreditAdapter
from .wallet import EasyPaisaAdapter, JazzCashAdapter, RaastAdapter


_ADAPTERS: dict[str, PaymentAdapter] = {
    a.method: a for a in (
        CashAdapter(),
        CardCreditAdapter(),
        CardDebitAdapter(),
        EasyPaisaAdapter(),
        JazzCashAdapter(),
        RaastAdapter(),
        BankTransferAdapter(),
        StoreCreditAdapter(),
        ChequeAdapter(),
    )
}


def get_adapter(method: str) -> PaymentAdapter:
    try:
        return _ADAPTERS[method]
    except KeyError as exc:
        raise PaymentValidationError({"payment_method": f"Unknown method: {method!r}"}) from exc


def all_methods() -> list[str]:
    return list(_ADAPTERS.keys())


__all__ = [
    "PaymentAdapter",
    "PaymentValidationError",
    "get_adapter",
    "all_methods",
]
