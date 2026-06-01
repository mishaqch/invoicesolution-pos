"""SDC (Fiscalization Service) submission path.

When FBR_SDC_BASE_URL is set and an invoice's branch has an FBR POS ID, the
submission goes to the SDC (POSID per-request) instead of the DI-API gateway.
We mock the SDC HTTP call and assert: the branch's POSID is sent, the returned
fiscal number + QR persist, and the invoice goes valid. DI-API tenants (no SDC
configured) are unaffected.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.tasks import submit_invoice_to_fbr
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice
from apps.sales.services import checkout
from apps.tenants.models import Branch, Terminal
from apps.accounts.models import User


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="PEER TRADERS", code="PT1", address="x",
        city="Lahore", province="PUNJAB",
        fbr_pos_id="194444", fbr_pos_code="3364862B",
    )


@pytest.fixture
def setup(db, tenant, branch, owner_user):
    term = Terminal.objects.create(tenant=tenant, branch=branch, name="C1",
                                   device_fingerprint="sdc-" + uuid.uuid4().hex[:8])
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="Item", sku="SDC-1", uom=uom,
                               sale_price=Decimal("100"), cost_price=Decimal("50"))
    record_movement(tenant_id=tenant.id, product=p, branch=branch,
                    movement_type="opening_balance", quantity=Decimal("50"))
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=term, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(p.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "18", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "118"}],
        client_uuid=str(uuid.uuid4()),
    )
    return inv


def _mock_sdc_post(captured):
    """Patch requests.post in sdc_client to mimic the SDC fiscal response."""
    def fake_post(url, json=None, timeout=None, **kw):
        captured["url"] = url
        captured["body"] = json

        class _R:
            status_code = 200
            text = "ok"

            def json(self_inner):
                # SDC-shaped success: fiscal number + QR
                return {
                    "InvoiceNumber": "7000000788673600000FISCAL",
                    "QRCode": "data:image/png;base64,QRDATA",
                    "POSID": json.get("POSID"),
                }
        return _R()
    return patch("apps.fbr.sdc_client.requests.post", side_effect=fake_post)


@pytest.mark.django_db
def test_sdc_path_used_when_configured_and_branch_has_posid(settings, setup, tenant):
    settings.FBR_SDC_BASE_URL = "http://sdc-host:8524"
    inv = setup
    captured = {}
    with _mock_sdc_post(captured):
        result = submit_invoice_to_fbr(str(inv.id))

    # Went via SDC
    assert result.get("via") == "sdc", result
    assert result.get("ok") is True
    # Correct endpoint + per-branch POSID sent
    assert captured["url"] == "http://sdc-host:8524/api/IMSFiscal/GetInvoiceNumberByModel"
    assert captured["body"]["POSID"] == 194444
    # Fiscal number + QR persisted, invoice valid
    inv.refresh_from_db()
    assert inv.status == "valid"
    assert inv.fbr_invoice_number == "7000000788673600000FISCAL"
    assert inv.fbr_qr_payload  # QR present (from SDC)


@pytest.mark.django_db
def test_di_api_path_when_sdc_not_configured(settings, setup, tenant):
    """No FBR_SDC_BASE_URL → must NOT use the SDC; falls through to DI-API
    (which defers cleanly here since no tenant token is set)."""
    settings.FBR_SDC_BASE_URL = ""
    inv = setup
    with patch("apps.fbr.sdc_client.requests.post") as sdc_post:
        result = submit_invoice_to_fbr(str(inv.id))
    sdc_post.assert_not_called()  # SDC never touched
    # No token configured → DI-API path defers (not an SDC result)
    assert result.get("via") != "sdc"


@pytest.mark.django_db
def test_sdc_skipped_when_branch_has_no_posid(settings, db, tenant, owner_user):
    """SDC configured but branch has NO POS ID → don't use SDC (DI-API tenant)."""
    settings.FBR_SDC_BASE_URL = "http://sdc-host:8524"
    br = Branch.objects.create(tenant=tenant, name="DI Branch", code="DIB",
                               address="x", city="x", province="PUNJAB")  # no fbr_pos_id
    term = Terminal.objects.create(tenant=tenant, branch=br, name="C1",
                                   device_fingerprint="no-pos-" + uuid.uuid4().hex[:8])
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="Item", sku="DI-1", uom=uom,
                               sale_price=Decimal("100"), cost_price=Decimal("50"))
    record_movement(tenant_id=tenant.id, product=p, branch=br,
                    movement_type="opening_balance", quantity=Decimal("10"))
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=br, terminal=term, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(p.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "18", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "118"}],
        client_uuid=str(uuid.uuid4()),
    )
    with patch("apps.fbr.sdc_client.requests.post") as sdc_post:
        result = submit_invoice_to_fbr(str(inv.id))
    sdc_post.assert_not_called()
    assert result.get("via") != "sdc"
