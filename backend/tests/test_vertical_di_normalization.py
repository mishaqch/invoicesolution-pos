"""Vertical is a POS concept — a Digital-Invoicing-only tenant should never
carry a pharmacy/restaurant vertical. normalise_vertical_for_mode() collapses
it to the neutral default for DI tenants, and the Tenant admin form applies it
on save.
"""

from __future__ import annotations

from apps.tenants.business_mode import DEFAULT_VERTICAL, normalise_vertical_for_mode


def test_di_mode_collapses_vertical_to_default():
    assert normalise_vertical_for_mode("digital_invoicing", "restaurant") == DEFAULT_VERTICAL
    assert normalise_vertical_for_mode("digital_invoicing", "pharmacy") == DEFAULT_VERTICAL
    assert normalise_vertical_for_mode("digital_invoicing", None) == DEFAULT_VERTICAL


def test_pos_and_both_keep_vertical():
    assert normalise_vertical_for_mode("pos", "restaurant") == "restaurant"
    assert normalise_vertical_for_mode("both", "pharmacy") == "pharmacy"
    # Missing vertical falls back to the default, not blank.
    assert normalise_vertical_for_mode("pos", None) == DEFAULT_VERTICAL


def test_none_mode_defaults_to_di_behaviour():
    # DEFAULT_BUSINESS_MODE is digital_invoicing, so a missing mode collapses.
    assert normalise_vertical_for_mode(None, "restaurant") == DEFAULT_VERTICAL
