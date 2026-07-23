"""Card adapter input validation — the mandatory-vs-optional card-detail rule.

The POS terminal (require_details=True, the default) MUST have card_last4 +
card_auth_code. Back-office MANUAL invoicing (require_details=False) may omit
them, but any value that IS supplied still has to be the right shape.
"""

from __future__ import annotations

import pytest

from apps.payments.adapters.base import PaymentValidationError
from apps.payments.adapters.card import CardCreditAdapter


@pytest.fixture
def adapter() -> CardCreditAdapter:
    return CardCreditAdapter()


# --- terminal / strict default (require_details=True) -----------------------

def test_terminal_requires_card_fields(adapter):
    """Empty card fields at the POS terminal are rejected."""
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({})


def test_terminal_happy_path(adapter):
    clean = adapter.validate_input(
        {"card_last4": "4242", "card_auth_code": "123456", "card_rrn": "RRN99"},
    )
    assert clean["card_last4"] == "4242"
    assert clean["card_auth_code"] == "123456"
    assert clean["card_rrn"] == "RRN99"


# --- manual / lenient (require_details=False) -------------------------------

def test_manual_allows_missing_card_fields(adapter):
    """Manual invoicing may omit card_last4 / card_auth_code entirely."""
    clean = adapter.validate_input({}, require_details=False)
    assert clean["card_last4"] is None
    assert clean["card_auth_code"] is None


def test_manual_still_validates_supplied_values(adapter):
    """Optional does not mean unchecked: a bad last4 is still rejected."""
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({"card_last4": "12"}, require_details=False)


def test_manual_accepts_valid_supplied_values(adapter):
    clean = adapter.validate_input(
        {"card_last4": "4242", "card_auth_code": "123456"},
        require_details=False,
    )
    assert clean["card_last4"] == "4242"
    assert clean["card_auth_code"] == "123456"
