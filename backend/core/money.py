"""Money utility — the single home for monetary arithmetic.

Storage precision: 4 decimals (`DECIMAL(14, 4)`).
Display precision: 2 decimals.
Tax math: per-line round to 4 decimals, then sum, then round display to 2.

Per CLAUDE.md: never `float`. Anything in this codebase that touches a
monetary value goes through this module on the Python side, or the
matching paisa-integer utility on the JS side.

Test invariants (in tests/test_phase2_money.py):
  * Rs 1000 × 18% == Rs 180.00 exactly (no float drift).
  * Multi-line tax sums match per-line tax sums to 4dp.
  * Money.zero() + arbitrary amount == that amount.
  * Money.from_str('1.5') is exact (no binary-float surprises).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Self

STORAGE_QUANT = Decimal("0.0001")  # 4 decimal places
DISPLAY_QUANT = Decimal("0.01")    # 2 decimal places
ZERO = Decimal("0.0000")


@dataclass(frozen=True)
class Money:
    """Immutable wrapper around Decimal, quantized to 4dp at construction."""

    amount: Decimal

    @classmethod
    def zero(cls) -> "Money":
        return cls(ZERO)

    @classmethod
    def from_str(cls, s: str | Decimal) -> "Money":
        if isinstance(s, Money):
            return s
        return cls(Decimal(str(s)).quantize(STORAGE_QUANT, rounding=ROUND_HALF_UP))

    @classmethod
    def from_paisa(cls, paisa: int) -> "Money":
        return cls(Decimal(paisa) / Decimal(100))

    def __post_init__(self):
        # Force-quantize on the way in so equality holds across constructors.
        object.__setattr__(
            self,
            "amount",
            Decimal(self.amount).quantize(STORAGE_QUANT, rounding=ROUND_HALF_UP),
        )

    # --- Arithmetic --------------------------------------------------------

    def __add__(self, other: "Money") -> "Money":
        return Money.from_str(self.amount + other.amount)

    def __sub__(self, other: "Money") -> "Money":
        return Money.from_str(self.amount - other.amount)

    def __neg__(self) -> "Money":
        return Money.from_str(-self.amount)

    def __mul__(self, scalar: int | Decimal | str) -> "Money":
        return Money.from_str(self.amount * Decimal(str(scalar)))

    __rmul__ = __mul__

    def __lt__(self, other: "Money") -> bool: return self.amount < other.amount
    def __le__(self, other: "Money") -> bool: return self.amount <= other.amount
    def __gt__(self, other: "Money") -> bool: return self.amount > other.amount
    def __ge__(self, other: "Money") -> bool: return self.amount >= other.amount

    def is_zero(self) -> bool: return self.amount == ZERO
    def is_positive(self) -> bool: return self.amount > ZERO
    def is_negative(self) -> bool: return self.amount < ZERO

    # --- Display -----------------------------------------------------------

    def display(self) -> str:
        """Two-decimal string for receipts/UI."""
        return str(self.amount.quantize(DISPLAY_QUANT, rounding=ROUND_HALF_UP))

    def __str__(self) -> str:
        return str(self.amount)

    def __repr__(self) -> str:
        return f"Money({self.amount})"


# ---------------------------------------------------------------------------
# Tax helpers
# ---------------------------------------------------------------------------


def apply_tax(net: Money, rate_pct: Decimal | str | float) -> tuple[Money, Money]:
    """Return (gross, tax_amount) given a net amount and a tax rate %.

    rate_pct: 18 (not 0.18), to match the schema's DECIMAL(5,2) %.
    """
    rate = Decimal(str(rate_pct)) / Decimal(100)
    tax = Money.from_str(net.amount * rate)
    return net + tax, tax


def sum_money(items: Iterable[Money]) -> Money:
    total = Money.zero()
    for m in items:
        total = total + m
    return total
