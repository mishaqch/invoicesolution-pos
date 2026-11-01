"""The payment method decides the services tax rate — enforced on the SERVER.

TDCP's rule (PRA/Punjab): a bill paid entirely by card is taxed at the reduced
rate (8%); any cash in the tender means the standard rate (16%) on the whole
bill.

This lived only in the clients. The terminal's payment screen swapped the rate
before sending, admin-web did its own swap, and the server simply trusted
whatever rate arrived. Two consequences at TDCP:

  * the hotel folio checkout has its own payment picker and never swapped at
    all, so a card-paying guest saw 8% promised and was charged 16%; and
  * any terminal running an older build kept sending 16% regardless.

So the rule belongs here, where every path converges and no stale .exe can
bypass it.

Rooms are deliberately exempt. A TDCP room night carries a FIXED declared tax
(VIP 8820 base + 1680 tax = 10500/night, ~19.05%) set by the resort's tariff,
not a percentage we are free to recompute — re-rating it would change the
advertised room price.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.sales.services.tax_rules import (
    is_fully_card,
    resolve_services_rate,
)

pytestmark = pytest.mark.django_db


class FakeTenant:
    """Only the two rate fields matter to the rule."""

    def __init__(self, standard="16.00", card="8.00", vertical="restaurant"):
        self.services_tax_rate_standard = Decimal(standard) if standard else None
        self.services_tax_rate_card = Decimal(card) if card else None
        self.vertical = vertical


# --- is_fully_card -------------------------------------------------------

@pytest.mark.parametrize("methods,expected", [
    ([], False),                                  # no tender yet → standard
    (["card_credit"], True),
    (["card_debit"], True),
    (["card_credit", "card_debit"], True),        # split across two cards
    (["cash"], False),
    (["card_credit", "cash"], False),             # ANY cash → standard rate
    (["cash", "card_credit"], False),
    (["easypaisa"], False),                       # wallet is not a card
    (["card_credit", "easypaisa"], False),
])
def test_is_fully_card(methods, expected):
    payments = [{"payment_method": m, "amount": "100"} for m in methods]
    assert is_fully_card(payments) is expected


def test_zero_amount_card_tender_does_not_buy_the_discount():
    """A Rs 0 card line must not turn a cash bill into a card bill."""
    payments = [
        {"payment_method": "cash", "amount": "1000"},
        {"payment_method": "card_credit", "amount": "0"},
    ]
    assert is_fully_card(payments) is False


# --- resolve_services_rate ----------------------------------------------

def test_card_payment_drops_food_to_the_reduced_rate():
    tenant = FakeTenant()
    lines = [{"tax_rate": "16.00", "is_taxable": True}]
    out = resolve_services_rate(lines, tenant=tenant, fully_card=True)
    assert out[0]["tax_rate"] == "8.00"


def test_cash_payment_uses_the_standard_rate():
    tenant = FakeTenant()
    lines = [{"tax_rate": "8.00", "is_taxable": True}]
    out = resolve_services_rate(lines, tenant=tenant, fully_card=False)
    assert out[0]["tax_rate"] == "16.00", "a cash bill must be re-rated UP to 16%"


def test_the_amount_follows_the_rate_not_just_the_label():
    """THE reported bug: the receipt said 8% but the money was 16%."""
    from apps.sales.services.pricing import quote_cart

    tenant = FakeTenant()
    lines = [{"quantity": "1", "unit_price": "1000.00",
              "tax_rate": "16.00", "is_taxable": True}]

    card = quote_cart(resolve_services_rate(lines, tenant=tenant, fully_card=True))
    cash = quote_cart(resolve_services_rate(lines, tenant=tenant, fully_card=False))

    assert card.tax_total.amount == Decimal("80.0000"), "8% of 1000"
    assert card.grand_total.amount == Decimal("1080.0000")
    assert cash.tax_total.amount == Decimal("160.0000"), "16% of 1000"
    assert cash.grand_total.amount == Decimal("1160.0000")


def test_a_room_night_keeps_its_declared_fixed_tax():
    """VIP 8820 + 1680 = 10500/night is the resort's tariff, not a percentage."""
    tenant = FakeTenant()
    room = {"quantity": "1", "unit_price": "8820.0000",
            "tax_rate": "19.047619", "is_taxable": True, "is_room": True}

    out = resolve_services_rate([room], tenant=tenant, fully_card=True)

    assert out[0]["tax_rate"] == "19.047619", "a declared room tax must not be re-rated"


def test_a_room_and_food_on_one_card_bill_are_rated_independently():
    from apps.sales.services.pricing import quote_cart

    tenant = FakeTenant()
    lines = [
        {"quantity": "1", "unit_price": "8820.0000", "tax_rate": "19.047619",
         "is_taxable": True, "is_room": True},
        {"quantity": "1", "unit_price": "1000.00", "tax_rate": "16.00",
         "is_taxable": True},
    ]

    q = quote_cart(resolve_services_rate(lines, tenant=tenant, fully_card=True))

    # Room tax unchanged (1680), food at 8% (80).
    assert q.tax_total.amount == Decimal("1760.0000")
    assert q.grand_total.amount == Decimal("11580.0000")


def test_a_non_taxable_line_stays_non_taxable():
    tenant = FakeTenant()
    lines = [{"tax_rate": "0", "is_taxable": False}]
    out = resolve_services_rate(lines, tenant=tenant, fully_card=True)
    assert out[0]["is_taxable"] is False
    assert Decimal(out[0]["tax_rate"] or 0) == 0, "an exempt item must never be taxed"


def test_feature_is_off_when_the_tenant_has_no_card_rate():
    """Every other tenant must behave exactly as before."""
    tenant = FakeTenant(card=None)
    lines = [{"tax_rate": "16.00", "is_taxable": True}]
    out = resolve_services_rate(lines, tenant=tenant, fully_card=True)
    assert out[0]["tax_rate"] == "16.00", "no card rate configured → no swap"


def test_a_custom_rate_line_is_left_alone():
    """Only the two configured rates participate in the swap."""
    tenant = FakeTenant()
    lines = [{"tax_rate": "5.00", "is_taxable": True}]
    out = resolve_services_rate(lines, tenant=tenant, fully_card=True)
    assert out[0]["tax_rate"] == "5.00"


def test_is_idempotent():
    tenant = FakeTenant()
    lines = [{"tax_rate": "16.00", "is_taxable": True}]
    once = resolve_services_rate(lines, tenant=tenant, fully_card=True)
    twice = resolve_services_rate(once, tenant=tenant, fully_card=True)
    assert twice[0]["tax_rate"] == "8.00"


def test_the_input_lines_are_not_mutated():
    """Callers reuse their cart list; a hidden mutation would corrupt it."""
    tenant = FakeTenant()
    lines = [{"tax_rate": "16.00", "is_taxable": True}]
    resolve_services_rate(lines, tenant=tenant, fully_card=True)
    assert lines[0]["tax_rate"] == "16.00"
