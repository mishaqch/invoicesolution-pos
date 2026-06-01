"""POS/retail scenarioId derivation in the sandbox submission path.

A retailer selling to walk-in end consumers must report under the
retailer-end-consumer scenarios (SN026/SN027/SN028) when FBR has assigned
them — not the generic B2B SN001/SN002. We only emit a retail scenarioId when
it's in the tenant's assigned set (so we never send PRAL an unassigned one).

The derivation lives inline in tasks.submit_invoice_to_fbr; here we exercise
the same decision rules against constructed invoices via the real task, with
PRAL routed to the in-process mock.
"""
from __future__ import annotations

import json as _json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.models import FbrToken, FbrSubmission
from apps.fbr.tasks import submit_invoice_to_fbr
from apps.inventory.services.movements import record_movement
from apps.tenants.models import Branch, Terminal

MOCK_BASE = "http://testserver/__mock_pral"


def _login(api, email, password="testpass1234"):
    r = api.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


def _route_to_mock():
    from django.test import RequestFactory
    from apps.fbr import mock_pral
    rf = RequestFactory()

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        req = rf.post(
            "/__mock_pral/di_data/v1/di/postinvoicedata",
            data=_json.dumps(json or {}), content_type="application/json",
            HTTP_AUTHORIZATION=(headers or {}).get("Authorization", ""),
        )
        dresp = mock_pral.post_invoice(req)

        class _R:
            status_code = dresp.status_code
            text = dresp.content.decode()

            def json(self_inner):
                return _json.loads(dresp.content.decode())

        return _R()

    return patch("apps.fbr.client.requests.post", side_effect=fake_post)


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Shop", code="SH1",
        address="x", city="Karachi", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="retail-fp",
    )


@pytest.fixture
def product(db, tenant, branch):
    p = Product.objects.create(
        tenant=tenant, name="Item", sku="IT-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("1000"), cost_price=Decimal("600"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return p


def _sandbox_token(tenant):
    t = FbrToken.objects.create(
        tenant=tenant, environment="sandbox",
        token_encrypted="", api_endpoint=MOCK_BASE, is_active=True,
    )
    t.set_token("SANDBOX-BEARER-TOKEN")
    t.save()
    return t


def _make_walkin_invoice(api, branch, terminal, product):
    body = {
        "branch": str(branch.id), "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(product.id), "quantity": "1", "unit_price": "1000",
            "tax_rate": "18", "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r = api.post("/api/sales/invoices/manual/", body, format="json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def _scenario_sent(invoice_id):
    sub = (
        FbrSubmission.objects.filter(invoice_id=invoice_id)
        .order_by("-submitted_at").first()
    )
    assert sub is not None
    return (sub.request_payload or {}).get("scenarioId")


@pytest.mark.django_db
def test_retail_tenant_walkin_uses_sn026(tenant, branch, terminal, product, owner_user):
    """Retailer assigned SN026 → walk-in standard sale derives SN026."""
    tenant.assigned_scenarios = ["SN001", "SN002", "SN026"]
    tenant.save(update_fields=["assigned_scenarios"])
    _sandbox_token(tenant)
    api = APIClient(); _login(api, owner_user.email)
    inv = _make_walkin_invoice(api, branch, terminal, product)
    with _route_to_mock():
        submit_invoice_to_fbr(inv)
    assert _scenario_sent(inv) == "SN026"


@pytest.mark.django_db
def test_non_retail_tenant_walkin_uses_sn002(tenant, branch, terminal, product, owner_user):
    """Tenant NOT assigned SN026 → falls back to SN002 (unchanged behaviour)."""
    tenant.assigned_scenarios = ["SN001", "SN002"]
    tenant.save(update_fields=["assigned_scenarios"])
    _sandbox_token(tenant)
    api = APIClient(); _login(api, owner_user.email)
    inv = _make_walkin_invoice(api, branch, terminal, product)
    with _route_to_mock():
        submit_invoice_to_fbr(inv)
    assert _scenario_sent(inv) == "SN002"
