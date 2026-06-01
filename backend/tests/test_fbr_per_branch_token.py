"""Per-branch FBR token routing for POS.

Each POS branch has its own bearer token (BranchFbrToken). A sale from a
branch must be submitted under THAT branch's token — never the tenant token
or another branch's. Digital Invoicing tenants (no branch token) keep using
the tenant-level token. We assert by capturing the Authorization header the
mock PRAL gateway received.
"""
from __future__ import annotations

import json as _json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.models import BranchFbrToken, FbrToken
from apps.fbr.tasks import submit_invoice_to_fbr
from apps.inventory.services.movements import record_movement
from apps.tenants.models import Branch, Terminal

MOCK_BASE = "http://testserver/__mock_pral"


def _login(api, email, password="testpass1234"):
    r = api.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


def _route_to_mock(captured):
    """Route FbrClient.requests.post into mock_pral and capture the bearer."""
    from django.test import RequestFactory
    from apps.fbr import mock_pral
    rf = RequestFactory()

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        captured["auth"] = (headers or {}).get("Authorization", "")
        req = rf.post(
            "/__mock_pral/di_data/v1/di/postinvoicedata",
            data=_json.dumps(json or {}), content_type="application/json",
            HTTP_AUTHORIZATION=captured["auth"],
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
        tenant=tenant, name="PEER TRADERS", code="PT1",
        address="x", city="Karachi", province="SINDH",
        fbr_pos_id="194444", fbr_pos_code="3364862B",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="pb-fp",
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


def _make_invoice(api, branch, terminal, product):
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


@pytest.mark.django_db
def test_branch_token_used_over_tenant_token(tenant, branch, terminal, product, owner_user):
    """Branch has its own token AND the tenant has a different one →
    submission must use the BRANCH token."""
    # Tenant-level token (would be used by DI) — production, sandbox-shaped env.
    t_tok = FbrToken.objects.create(
        tenant=tenant, environment="sandbox",
        token_encrypted="", api_endpoint=MOCK_BASE, is_active=True,
    )
    t_tok.set_token("TENANT-LEVEL-TOKEN")
    t_tok.save()
    # Branch (POS) token — what PEER TRADERS would actually have.
    b_tok = BranchFbrToken.objects.create(
        tenant=tenant, branch=branch, environment="sandbox",
        token_encrypted="", api_endpoint=MOCK_BASE, is_active=True,
    )
    b_tok.set_token("840a2665-e8b2-34ac-87b3-bee52e7dff57")
    b_tok.save()
    # Mock requires a scenarioId (sandbox) → give the tenant one.
    tenant.assigned_scenarios = ["SN002"]
    tenant.save(update_fields=["assigned_scenarios"])

    api = APIClient(); _login(api, owner_user.email)
    inv = _make_invoice(api, branch, terminal, product)

    captured = {}
    with _route_to_mock(captured):
        submit_invoice_to_fbr(inv)

    assert captured["auth"] == "Bearer 840a2665-e8b2-34ac-87b3-bee52e7dff57"


@pytest.mark.django_db
def test_no_branch_token_falls_back_to_tenant_token(tenant, branch, terminal, product, owner_user):
    """No branch token → Digital Invoicing path: use the tenant token."""
    t_tok = FbrToken.objects.create(
        tenant=tenant, environment="sandbox",
        token_encrypted="", api_endpoint=MOCK_BASE, is_active=True,
    )
    t_tok.set_token("TENANT-LEVEL-TOKEN")
    t_tok.save()
    tenant.assigned_scenarios = ["SN002"]
    tenant.save(update_fields=["assigned_scenarios"])

    api = APIClient(); _login(api, owner_user.email)
    inv = _make_invoice(api, branch, terminal, product)

    captured = {}
    with _route_to_mock(captured):
        submit_invoice_to_fbr(inv)

    assert captured["auth"] == "Bearer TENANT-LEVEL-TOKEN"


@pytest.mark.django_db
def test_inactive_branch_token_defers_no_fallback(tenant, branch, terminal, product, owner_user):
    """Branch token exists but is inactive → defer; do NOT fall back to the
    tenant token (would mis-attribute the sale to the wrong registration)."""
    tt = FbrToken.objects.create(
        tenant=tenant, environment="sandbox", token_encrypted="",
        api_endpoint=MOCK_BASE, is_active=True,
    )
    tt.set_token("TENANT-LEVEL-TOKEN")
    tt.save()
    b_tok = BranchFbrToken.objects.create(
        tenant=tenant, branch=branch, environment="sandbox", token_encrypted="",
        api_endpoint=MOCK_BASE, is_active=False,
    )
    b_tok.set_token("BRANCH-TOKEN")
    b_tok.save()

    api = APIClient(); _login(api, owner_user.email)
    inv = _make_invoice(api, branch, terminal, product)

    result = submit_invoice_to_fbr(inv)
    assert result == {"deferred": "branch_token_inactive"}


# --- Service-layer: activate / deactivate a branch POS token ---------------


@pytest.mark.django_db
def test_activate_branch_token_no_scenario_gate(tenant, branch):
    """A branch token activates immediately — POS has no sandbox/scenario
    gate (unlike tenant production activation)."""
    from apps.fbr.services import activate_branch_token

    obj = activate_branch_token(
        branch=branch, token="840a2665-e8b2-34ac-87b3-bee52e7dff57",
        api_endpoint="https://gw.fbr.gov.pk",
    )
    assert obj.is_active is True
    assert obj.environment == "production"
    assert obj.branch_id == branch.id
    assert obj.tenant_id == branch.tenant_id
    assert obj.token == "840a2665-e8b2-34ac-87b3-bee52e7dff57"


@pytest.mark.django_db
def test_activate_branch_token_endpoint_only_update(tenant, branch):
    """Empty token updates only the endpoint, keeping the stored bearer."""
    from apps.fbr.services import activate_branch_token

    activate_branch_token(
        branch=branch, token="ORIGINAL-BEARER-TOKEN",
        api_endpoint="https://gw.fbr.gov.pk",
    )
    obj = activate_branch_token(
        branch=branch, token="", api_endpoint="https://gw.fbr.gov.pk",
    )
    assert obj.token == "ORIGINAL-BEARER-TOKEN"  # unchanged


@pytest.mark.django_db
def test_activate_branch_token_first_time_requires_token(tenant, branch):
    from django.core.exceptions import ValidationError

    from apps.fbr.services import activate_branch_token

    with pytest.raises(ValidationError):
        activate_branch_token(
            branch=branch, token="", api_endpoint="https://gw.fbr.gov.pk",
        )


@pytest.mark.django_db
def test_deactivate_branch_token(tenant, branch):
    from apps.fbr.services import activate_branch_token, deactivate_branch_token

    activate_branch_token(
        branch=branch, token="SOME-BEARER-TOKEN",
        api_endpoint="https://gw.fbr.gov.pk",
    )
    assert deactivate_branch_token(branch=branch) is True
    bt = BranchFbrToken.objects.get(branch=branch, environment="production")
    assert bt.is_active is False
    # Re-deactivating is a no-op.
    assert deactivate_branch_token(branch=branch) is False
