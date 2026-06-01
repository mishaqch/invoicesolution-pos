"""Multiple terminals per branch, all sharing the branch's FBR token.

A branch can have several POS terminals. Each terminal:
  - gets a stable per-branch terminal_index → collision-free invoice numbers
    (…-T1-… vs …-T2-…) even under the (tenant, local_invoice_number) unique
    constraint,
  - submits invoices under the SAME branch FBR token,
  - receives its own per-invoice FBR number + QR back.
"""
from __future__ import annotations

import json as _json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.models import BranchFbrToken
from apps.fbr.tasks import submit_invoice_to_fbr
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal

MOCK_BASE = "http://testserver/__mock_pral"


def _login(api, email, password="testpass1234"):
    r = api.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


def _route_to_mock(captured):
    from django.test import RequestFactory
    from apps.fbr import mock_pral
    rf = RequestFactory()

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        captured.append((headers or {}).get("Authorization", ""))
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
        tenant=tenant, name="PEER TRADERS", code="PT1",
        address="x", city="Karachi", province="SINDH",
        fbr_pos_id="194444", fbr_pos_code="3364862B",
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
        movement_type="opening_balance", quantity=Decimal("1000"),
    )
    return p


def _sale(api, branch, terminal, product):
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
def test_terminals_get_distinct_indexes(tenant, branch):
    t1 = Terminal.objects.create(tenant=tenant, branch=branch, name="Counter",
                                 device_fingerprint="mt-fp-1")
    t2 = Terminal.objects.create(tenant=tenant, branch=branch, name="Counter",
                                 device_fingerprint="mt-fp-2")
    t3 = Terminal.objects.create(tenant=tenant, branch=branch, name="Counter",
                                 device_fingerprint="mt-fp-3")
    # Same name → would have collided under the old name-derived index; now each
    # gets a distinct per-branch ordinal.
    assert {t1.terminal_index, t2.terminal_index, t3.terminal_index} == {1, 2, 3}


@pytest.mark.django_db
def test_two_terminals_same_branch_no_number_collision_and_same_token(
    tenant, branch, product, owner_user,
):
    # Branch (POS) token shared by both terminals.
    bt = BranchFbrToken.objects.create(
        tenant=tenant, branch=branch, environment="sandbox",
        token_encrypted="", api_endpoint=MOCK_BASE, is_active=True,
    )
    bt.set_token("840a2665-e8b2-34ac-87b3-bee52e7dff57")
    bt.save()
    tenant.assigned_scenarios = ["SN002"]
    tenant.save(update_fields=["assigned_scenarios"])

    t1 = Terminal.objects.create(tenant=tenant, branch=branch, name="Counter A",
                                 device_fingerprint="mt-a")
    t2 = Terminal.objects.create(tenant=tenant, branch=branch, name="Counter B",
                                 device_fingerprint="mt-b")

    api = APIClient(); _login(api, owner_user.email)
    inv1 = _sale(api, branch, t1, product)
    inv2 = _sale(api, branch, t2, product)

    i1 = Invoice.objects.get(pk=inv1)
    i2 = Invoice.objects.get(pk=inv2)
    # Distinct numbers, distinct terminal segments → no unique-constraint clash.
    assert i1.local_invoice_number != i2.local_invoice_number
    assert f"-T{t1.terminal_index}-" in i1.local_invoice_number
    assert f"-T{t2.terminal_index}-" in i2.local_invoice_number

    # Both submit under the SAME branch token and each gets its own FBR number.
    captured = []
    with _route_to_mock(captured):
        submit_invoice_to_fbr(inv1)
        submit_invoice_to_fbr(inv2)

    assert captured == [
        "Bearer 840a2665-e8b2-34ac-87b3-bee52e7dff57",
        "Bearer 840a2665-e8b2-34ac-87b3-bee52e7dff57",
    ]
    i1.refresh_from_db(); i2.refresh_from_db()
    assert i1.status == "valid" and i1.fbr_invoice_number and i1.fbr_qr_payload
    assert i2.status == "valid" and i2.fbr_invoice_number and i2.fbr_qr_payload
    # Per-invoice results are independent.
    assert i1.fbr_invoice_number != i2.fbr_invoice_number


@pytest.mark.django_db
def test_terminal_from_other_branch_rejected(tenant, branch, product, owner_user):
    """A terminal registered to branch B can't post an invoice for branch A."""
    other = Branch.objects.create(
        tenant=tenant, name="Other", code="OTH",
        address="x", city="Lahore", province="PUNJAB",
    )
    foreign_terminal = Terminal.objects.create(
        tenant=tenant, branch=other, name="X", device_fingerprint="foreign",
    )
    api = APIClient(); _login(api, owner_user.email)
    body = {
        "branch": str(branch.id), "terminal": str(foreign_terminal.id),
        "cart_lines": [{
            "product": str(product.id), "quantity": "1", "unit_price": "1000",
            "tax_rate": "18", "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r = api.post("/api/sales/invoices/manual/", body, format="json")
    assert r.status_code >= 400  # rejected by the branch/terminal consistency guard
