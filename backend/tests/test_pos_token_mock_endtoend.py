"""End-to-end POS → FBR submission against the LOCAL MOCK gateway.

Safe full-flow proof that our system can take a POS sale, build the PRAL
payload, authenticate with the real Saeed Electronics token format, submit,
and persist the returned FBR invoice number + QR — WITHOUT any real FBR
traffic. `requests.post`/`get` are routed into apps.fbr.mock_pral via Django's
test client, so nothing leaves the process.

This complements the read-only live probe (which returned 403/900908 because
this host's IP isn't PRAL-whitelisted — expected; real submits must originate
from the whitelisted central server).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.models import FbrToken
from apps.fbr.tasks import submit_invoice_to_fbr
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal

# The real Saeed Electronics POS credentials (POS ID 141721) — used here only
# to prove the token *format* flows through our pipeline. The mock gateway
# accepts any non-empty Bearer, so no secret is exercised against real FBR.
SAEED_TOKEN = "7311006b-f73b-305a-80b9-5032d4db87c4"
SAEED_POS_ID = "141721"
SAEED_POS_CODE = "5396FB55"

# Mock gateway base: FbrClient appends /di_data/v1/di/<endpoint>. The mock is
# mounted at /__mock_pral/di_data/v1/di/postinvoicedata (DEBUG-only).
MOCK_BASE = "http://testserver/__mock_pral"


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Saeed Electronics", code="SE1",
        address="Karachi", city="Karachi", province="SINDH",
        fbr_pos_id=SAEED_POS_ID, fbr_pos_code=SAEED_POS_CODE,
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter-1",
        device_fingerprint="saeed-fp-1",
    )


@pytest.fixture
def stocked_product(db, tenant, branch):
    p = Product.objects.create(
        tenant=tenant, name="LED Bulb", sku="LED-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("1000"), cost_price=Decimal("600"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return p


def _route_to_mock():
    """Route FbrClient's outbound requests.post straight into the mock_pral
    view function. We call the view directly (via RequestFactory) rather than
    the test Client so the app's own JWT auth middleware doesn't intercept the
    PRAL Bearer header — we're emulating PRAL's gateway, not our app's API."""
    import json as _json

    from django.test import RequestFactory

    from apps.fbr import mock_pral

    rf = RequestFactory()

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        body = _json.dumps(json or {})
        req = rf.post(
            "/__mock_pral/di_data/v1/di/postinvoicedata",
            data=body, content_type="application/json",
            HTTP_AUTHORIZATION=(headers or {}).get("Authorization", ""),
        )
        django_resp = mock_pral.post_invoice(req)  # JsonResponse

        class _R:
            status_code = django_resp.status_code
            text = django_resp.content.decode()

            def json(self_inner):
                return _json.loads(django_resp.content.decode())

        return _R()

    return patch("apps.fbr.client.requests.post", side_effect=fake_post)


@pytest.mark.django_db
def test_pos_sale_submits_and_validates_against_mock(
    tenant, branch, terminal, owner_user, stocked_product,
):
    # 1) Configure the token = Saeed token, endpoint = mock. We use the
    # SANDBOX environment here because the local mock gateway emulates PRAL's
    # sandbox contract (it requires a scenarioId). Production payloads omit
    # scenarioId by design, so a production-env run would be (correctly)
    # rejected by the sandbox mock. The token + pipeline are identical either
    # way — only scenarioId inclusion differs. Real go-live uses production.
    tok = FbrToken.objects.create(
        tenant=tenant, environment="sandbox",
        token_encrypted="", api_endpoint=MOCK_BASE, is_active=True,
    )
    tok.set_token(SAEED_TOKEN)
    tok.save()
    # Mock requires scenarioId; the submission task derives it for sandbox
    # only when the tenant has assigned scenarios. Give it one so the derived
    # SN001/SN002 path produces a non-empty scenarioId.
    tenant.assigned_scenarios = ["SN002"]
    tenant.save(update_fields=["assigned_scenarios"])

    # 2) Ring up a POS sale through the real checkout endpoint.
    api = APIClient()
    _login(api, owner_user.email)
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "2", "unit_price": "1000",
            "tax_rate": "18", "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "2360"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        resp = api.post("/api/sales/invoices/manual/", body, format="json")
    assert resp.status_code == 201, resp.content
    invoice_id = resp.json()["id"]

    # 3) Run the REAL submission task, with outbound HTTP routed to the mock.
    with _route_to_mock():
        result = submit_invoice_to_fbr(invoice_id)

    # 4) The invoice is now FBR-validated with a number + QR payload.
    assert result.get("ok") is True, result
    inv = Invoice.objects.get(pk=invoice_id)
    assert inv.status == "valid"
    assert inv.fbr_invoice_number, "expected an FBR invoice number"
    assert inv.fbr_qr_payload, "expected a QR payload for the receipt"
    # Proof the full POS→FBR pipeline ran with the Saeed token format and
    # produced a validated invoice + QR. (Sandbox mock; prod is identical
    # minus scenarioId.)
