"""Local-SDC fiscalization flow (browser/terminal on the branch machine).

The cloud server can't reach a branch's localhost SDC, so the client app
fiscalizes locally and posts the FBR number + QR back via /fiscal-result/.
This must be idempotent and anti-duplication: a second save (retry, double
click, two terminals) NEVER overwrites or duplicates the FBR number.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice
from apps.sales.services import checkout
from apps.tenants.models import Branch, Terminal


def _login(api, email, password="testpass1234"):
    r = api.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")


@pytest.fixture
def invoice(db, tenant, owner_user):
    br = Branch.objects.create(tenant=tenant, name="PEER TRADERS", code="PT1",
                               address="x", city="Lahore", province="PUNJAB",
                               fbr_pos_id="194444", fbr_pos_code="3364862B")
    term = Terminal.objects.create(tenant=tenant, branch=br, name="C1",
                                   device_fingerprint="sdcflow-" + uuid.uuid4().hex[:8])
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="Item", sku="LSDC-1", uom=uom,
                               sale_price=Decimal("100"), cost_price=Decimal("50"))
    record_movement(tenant_id=tenant.id, product=p, branch=br,
                    movement_type="opening_balance", quantity=Decimal("50"))
    return checkout.create_invoice(
        tenant_id=tenant.id, branch=br, terminal=term, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(p.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "18", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "118"}],
        client_uuid=str(uuid.uuid4()),
    )


@pytest.mark.django_db
def test_fiscal_payload_includes_branch_pos_id(invoice, owner_user):
    api = APIClient(); _login(api, owner_user.email)
    r = api.get(f"/api/sales/invoices/{invoice.id}/fiscal-payload/")
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["branch_fbr_pos_id"] == "194444"
    assert d["already_fiscalized"] is False
    assert d["sdc_payload"]["POSID"] == 194444
    assert d["sdc_payload"]["USIN"] == invoice.local_invoice_number


@pytest.mark.django_db
def test_fiscal_result_saves_then_is_idempotent(invoice, owner_user):
    api = APIClient(); _login(api, owner_user.email)
    # First save → stores the FBR number + QR, invoice goes valid.
    r1 = api.post(f"/api/sales/invoices/{invoice.id}/fiscal-result/",
                  {"fbr_invoice_number": "7000000788673600000FISCAL",
                   "qr_payload": "data:image/png;base64,QR"}, format="json")
    assert r1.status_code == 201, r1.content
    assert r1.json()["already"] is False
    invoice.refresh_from_db()
    assert invoice.status == "valid"
    assert invoice.fbr_invoice_number == "7000000788673600000FISCAL"
    assert invoice.fbr_qr_payload

    # Second save with a DIFFERENT number → must NOT overwrite (anti-dup),
    # returns the existing number with already=True.
    r2 = api.post(f"/api/sales/invoices/{invoice.id}/fiscal-result/",
                  {"fbr_invoice_number": "9999999999999999DIFFERENT"}, format="json")
    assert r2.status_code == 200, r2.content
    assert r2.json()["already"] is True
    assert r2.json()["fbr_invoice_number"] == "7000000788673600000FISCAL"
    invoice.refresh_from_db()
    assert invoice.fbr_invoice_number == "7000000788673600000FISCAL"  # unchanged


@pytest.mark.django_db
def test_fiscal_result_requires_number(invoice, owner_user):
    api = APIClient(); _login(api, owner_user.email)
    r = api.post(f"/api/sales/invoices/{invoice.id}/fiscal-result/", {}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_fiscal_payload_when_already_fiscalized(invoice, owner_user):
    api = APIClient(); _login(api, owner_user.email)
    api.post(f"/api/sales/invoices/{invoice.id}/fiscal-result/",
             {"fbr_invoice_number": "7000000788673600000FISCAL"}, format="json")
    r = api.get(f"/api/sales/invoices/{invoice.id}/fiscal-payload/")
    d = r.json()
    assert d["already_fiscalized"] is True
    assert d["sdc_payload"] is None  # nothing more to fiscalize
