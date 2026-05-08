"""Pricing tests — line discounts, cart discounts, taxable + zero-rated mix."""

from __future__ import annotations

from decimal import Decimal

from apps.sales.services.pricing import quote_cart, quote_line


def test_single_line_no_discount_no_tax():
    q = quote_line(quantity="1", unit_price="100", is_taxable=False)
    assert q.gross.amount == Decimal("100.0000")
    assert q.line_discount.amount == Decimal("0.0000")
    assert q.tax_amount.amount == Decimal("0.0000")
    assert q.line_total.amount == Decimal("100.0000")


def test_single_line_with_tax():
    q = quote_line(quantity="1", unit_price="1000", tax_rate="18")
    assert q.tax_amount.amount == Decimal("180.0000")
    assert q.line_total.amount == Decimal("1180.0000")


def test_line_with_pct_discount():
    q = quote_line(
        quantity="2", unit_price="500", discount_pct="10", tax_rate="18",
    )
    # gross 1000 - 10% (100) = 900 net; tax = 162; total = 1062
    assert q.gross.amount == Decimal("1000.0000")
    assert q.line_discount.amount == Decimal("100.0000")
    assert q.net.amount == Decimal("900.0000")
    assert q.tax_amount.amount == Decimal("162.0000")
    assert q.line_total.amount == Decimal("1062.0000")


def test_cart_two_lines_one_taxable_one_zero_rated():
    q = quote_cart([
        {"quantity": "1", "unit_price": "1000", "tax_rate": "18", "is_taxable": True},
        {"quantity": "2", "unit_price": "200", "tax_rate": "0", "is_taxable": False},
    ])
    # Line 1: gross 1000, tax 180, total 1180
    # Line 2: gross 400, tax 0, total 400
    assert q.subtotal.amount == Decimal("1400.0000")
    assert q.tax_total.amount == Decimal("180.0000")
    assert q.grand_total.amount == Decimal("1580.0000")


def test_cart_with_cart_level_discount():
    q = quote_cart(
        [
            {"quantity": "1", "unit_price": "1000", "tax_rate": "18", "is_taxable": True},
        ],
        cart_discount_pct="10",
    )
    # Line: net 1000, tax 180 → pre-cart-grand = 1180
    # Cart 10% on net 1000 = 100 → grand_total = 1180 - 100 = 1080
    assert q.cart_discount_amount.amount == Decimal("100.0000")
    assert q.grand_total.amount == Decimal("1080.0000")


def test_cart_clamp_when_discount_exceeds_subtotal():
    q = quote_cart(
        [
            {"quantity": "1", "unit_price": "100"},
        ],
        cart_discount_pct="500",
    )
    assert q.cart_discount_amount.amount == Decimal("100.0000")
    assert q.grand_total.amount == Decimal("0.0000")


def test_per_line_tax_then_sum_no_drift():
    """Tax is computed per-line at 4dp, then summed — no float-y drift."""
    q = quote_cart([
        {"quantity": "3", "unit_price": "33.33", "tax_rate": "18", "is_taxable": True},
        {"quantity": "1", "unit_price": "0.01", "tax_rate": "18", "is_taxable": True},
    ])
    # Line 1 tax: 99.99 * 0.18 = 17.9982
    # Line 2 tax: 0.01 * 0.18 = 0.0018
    # Sum = 18.0000 exactly
    assert q.tax_total.amount == Decimal("18.0000")
