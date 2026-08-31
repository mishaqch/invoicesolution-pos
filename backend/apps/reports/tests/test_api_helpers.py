"""Unit tests for the reports API/registry helper layer.

These exercise the pure request-shaping logic without spinning up the full
HTTP + auth middleware stack:
  * registry get/all_reports/names,
  * _build_filters coercing a JSON payload into a report's Filters dataclass
    (dropping unknown keys — the "filters" contract the frontend relies on).
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.reports import registry
from apps.reports.views import _build_filters


class TestRegistry:
    def test_get_known_report(self):
        assert registry.get("daily_sales").name == "daily_sales"

    def test_get_unknown_raises_keyerror(self):
        with pytest.raises(KeyError):
            registry.get("no_such_report")

    def test_all_reports_nonempty_and_named(self):
        allr = registry.all_reports()
        assert allr
        for name, cls in allr.items():
            assert cls.name == name

    def test_names_matches_all_reports(self):
        assert sorted(registry.names()) == sorted(registry.all_reports().keys())


class TestBuildFilters:
    def test_valid_keys_pass_through(self):
        R = registry.get("daily_sales")
        f = _build_filters(R, {"date_from": dt.date(2026, 1, 1), "branch_id": "abc"})
        assert f.date_from == dt.date(2026, 1, 1)
        assert f.branch_id == "abc"

    def test_unknown_keys_dropped(self):
        R = registry.get("daily_sales")
        # A stray/renamed field from the client must not blow up construction.
        f = _build_filters(R, {"branch_id": "abc", "bogus_field": 123})
        assert f.branch_id == "abc"
        assert not hasattr(f, "bogus_field")

    def test_empty_payload_yields_default_filters(self):
        R = registry.get("daily_sales")
        f = _build_filters(R, {})
        assert f.branch_id is None
        assert f.date_from is None
        assert f.date_to is None

    def test_none_payload_is_safe(self):
        R = registry.get("daily_sales")
        f = _build_filters(R, None)
        assert f.branch_id is None
