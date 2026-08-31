"""Smoke coverage for EVERY registered report.

Guarantees that each report:
  * is constructible with its own Filters(),
  * runs without raising (empty tenant AND with data),
  * returns a well-formed ReportResult (columns present, row_count == len(rows)),
  * honours the tenant boundary (never leaks another tenant's rows).

This is the "test each and every report" net — a new report added to the
registry is covered the moment it registers.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.reports.base import ReportResult
from apps.reports.registry import all_reports

pytestmark = pytest.mark.django_db

ALL = sorted(all_reports().items())
IDS = [n for n, _ in ALL]


@pytest.mark.parametrize("name,report_cls", ALL, ids=IDS)
class TestEveryReport:
    def test_runs_empty_without_error(self, name, report_cls, tenant):
        rep = report_cls(tenant_id=str(tenant.id), filters=report_cls.Filters())
        result = rep.run(use_cache=False)
        assert isinstance(result, ReportResult)
        assert result.row_count == len(result.rows)
        assert list(result.columns), f"{name} declares no columns"

    def test_runs_with_data_without_error(self, name, report_cls, tenant, make_invoice):
        make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        rep = report_cls(tenant_id=str(tenant.id), filters=report_cls.Filters())
        result = rep.run(use_cache=False)
        assert isinstance(result, ReportResult)
        assert result.row_count == len(result.rows)
        for row in result.rows:
            assert isinstance(row, dict)

    def test_tenant_isolation(self, name, report_cls, tenant, make_invoice):
        # Data belongs to `tenant`; a different tenant must not see sales rows.
        make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
        from apps.tenants.models import Tenant
        other = Tenant.objects.create(
            business_name="Other", ntn="OTHER-9", business_type="sole_proprietor",
            province="PUNJAB", fbr_connection_type="none",
        )
        rep = report_cls(tenant_id=str(other.id), filters=report_cls.Filters())
        result = rep.run(use_cache=False)
        assert result.row_count == len(result.rows)
