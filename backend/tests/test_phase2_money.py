"""Money utility tests — 100% coverage target on core/money.py."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.money import Money, apply_tax, sum_money


def test_zero():
    assert Money.zero().amount == Decimal("0.0000")


def test_from_str_quantizes():
    assert Money.from_str("1").amount == Decimal("1.0000")
    assert Money.from_str("1.5").amount == Decimal("1.5000")
    assert Money.from_str("1.23456").amount == Decimal("1.2346")  # half-up


def test_from_paisa():
    # 12345 paisa = Rs 123.45
    assert Money.from_paisa(12345).amount == Decimal("123.4500")


def test_addition_subtraction():
    a = Money.from_str("100.50")
    b = Money.from_str("0.50")
    assert (a + b).amount == Decimal("101.0000")
    assert (a - b).amount == Decimal("100.0000")


def test_negation_clamp_via_subtraction():
    a = Money.from_str("5.00")
    b = Money.from_str("12.00")
    assert (a - b).amount == Decimal("-7.0000")


def test_multiplication_by_scalar():
    # 1000 × 18% = 180.00 — the canonical case from CLAUDE.md.
    rs_1000 = Money.from_str("1000")
    rate = Decimal("0.18")
    tax = rs_1000 * rate
    assert tax.amount == Decimal("180.0000")
    assert tax.display() == "180.00"


def test_multiplication_with_quantity():
    # 1.5 kg × Rs 240/kg = Rs 360.00 exactly
    price = Money.from_str("240")
    qty = Decimal("1.5")
    assert (price * qty).amount == Decimal("360.0000")


def test_apply_tax_returns_gross_and_tax():
    net = Money.from_str("1000.00")
    gross, tax = apply_tax(net, Decimal("18"))
    assert tax.amount == Decimal("180.0000")
    assert gross.amount == Decimal("1180.0000")
    assert gross.display() == "1180.00"


def test_sum_money():
    items = [Money.from_str(x) for x in ("1.10", "2.20", "3.30")]
    assert sum_money(items).amount == Decimal("6.6000")


def test_comparison_operators():
    a = Money.from_str("5")
    b = Money.from_str("10")
    assert a < b
    assert a <= b
    assert b > a
    assert b >= a
    assert a.is_positive()
    assert (a - a).is_zero()
    assert (a - b).is_negative()


def test_immutability_through_arithmetic():
    a = Money.from_str("100")
    b = a + Money.from_str("50")
    # `a` should be unchanged.
    assert a.amount == Decimal("100.0000")
    assert b.amount == Decimal("150.0000")


def test_no_float_drift_under_repeated_addition():
    """Adding 0.1 a hundred times should give exactly 10.00, not 9.99 / 10.01."""
    total = Money.zero()
    for _ in range(100):
        total = total + Money.from_str("0.10")
    assert total.amount == Decimal("10.0000")
    assert total.display() == "10.00"


def test_display_rounds_half_up():
    # 1.235 with half-up rounding → 1.24
    assert Money.from_str("1.235").display() == "1.24"
    # Storage retains the 4dp value:
    assert Money.from_str("1.235").amount == Decimal("1.2350")
