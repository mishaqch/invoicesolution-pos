"""Regression tests for the report export endpoint.

The bug: DRF's content negotiation treated ?format=pdf|xlsx|csv as a request
for a renderer suffix, found none, and returned 404 BEFORE the view ran — so
every CSV/Excel/PDF download failed. These lock the fix: each format must
reach the view and return 200 with the right content type.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.reports import views

pytestmark = pytest.mark.django_db

FORMATS = ["pdf", "xlsx", "csv"]


def _export(name, fmt, user, tenant):
    factory = APIRequestFactory()
    req = factory.post(f"/api/reports/{name}/export/?format={fmt}", {}, format="json")
    force_authenticate(req, user=user)
    # The tenant-context middleware isn't in the unit request path; set it as
    # the middleware would.
    req.tenant = tenant
    req.tenant_id = str(tenant.id)
    return views.ReportExportView.as_view()(req, name=name)


@pytest.fixture
def advanced_tenant(tenant):
    # Exports require the reports_advanced module.
    tenant.modules_enabled = list(
        set((tenant.modules_enabled or [])) | {"reports_basic", "reports_advanced"}
    )
    tenant.save(update_fields=["modules_enabled"])
    return tenant


@pytest.mark.parametrize("fmt", FORMATS)
def test_export_does_not_404_on_format_query_param(fmt, advanced_tenant, cashier, make_invoice):
    make_invoice(grand_total=Decimal("100"), tax_total=Decimal("16"))
    resp = _export("daily_sales", fmt, cashier, advanced_tenant)
    assert resp.status_code == 200, f"{fmt} export returned {resp.status_code}"


@pytest.mark.parametrize("fmt", FORMATS)
def test_export_works_even_with_zero_rows(fmt, advanced_tenant, cashier):
    # An empty report must still export cleanly (a header-only file), not error.
    resp = _export("daily_sales", fmt, cashier, advanced_tenant)
    assert resp.status_code == 200


def test_unknown_report_still_404s(advanced_tenant, cashier):
    resp = _export("no_such_report", "pdf", cashier, advanced_tenant)
    assert resp.status_code == 404


def test_unsupported_format_rejected(advanced_tenant, cashier):
    resp = _export("daily_sales", "docx", cashier, advanced_tenant)
    assert resp.status_code == 400
