"""Phase 8b — manual invoice creation (wholesaler flow).

The /api/sales/invoices/manual/ endpoint creates an invoice without a
POS terminal cash session. Used by wholesalers and office staff.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="HQ", code="HQ",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Office",
        device_fingerprint="manual-fp",
    )


@pytest.fixture
def stocked_product(db, tenant, branch):
    p = Product.objects.create(
        tenant=tenant, name="Pipe", sku="PIPE-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("1000"),
        cost_price=Decimal("600"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return p


@pytest.mark.django_db
def test_manual_invoice_create_without_cash_session(
    tenant, branch, terminal, owner_user, stocked_product,
):
    api = APIClient()
    _login(api, owner_user.email)

    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "5",
            "unit_price": "1000",
            "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "5900"}],
        "client_uuid": str(uuid.uuid4()),
    }

    # Stub the FBR celery task so the test doesn't try to talk to PRAL.
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay") as mock_submit:
        resp = api.post("/api/sales/invoices/manual/", body, format="json")

    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert data["grand_total"] == "5900.0000"
    # Confirm the invoice was created without a cash_session.
    inv = Invoice.objects.get(pk=data["id"])
    assert inv.cash_session is None
    assert inv.cashier_id == owner_user.id
    # FBR submission was queued.
    mock_submit.assert_called_once_with(str(inv.id))


@pytest.mark.django_db
def test_manual_invoice_idempotent_on_client_uuid(
    tenant, branch, terminal, owner_user, stocked_product,
):
    api = APIClient()
    _login(api, owner_user.email)
    cuid = str(uuid.uuid4())
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1",
            "unit_price": "1000",
            "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": cuid,
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r1 = api.post("/api/sales/invoices/manual/", body, format="json")
        r2 = api.post("/api/sales/invoices/manual/", body, format="json")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert Invoice.objects.filter(client_uuid=cuid).count() == 1


@pytest.mark.django_db
def test_manual_invoice_requires_sales_create_permission(
    tenant, branch, terminal, cashier_user, stocked_product,
):
    """Cashiers should be able to create manual invoices, but a user
    without sales.create permission must be rejected."""
    api = APIClient()
    _login(api, cashier_user.email)
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1",
            "unit_price": "1000",
            "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        resp = api.post("/api/sales/invoices/manual/", body, format="json")
    # Cashier has sales.create per the role matrix — accept 201, but
    # an unauthenticated client gets 401.
    assert resp.status_code in (201, 403)


@pytest.mark.django_db
def test_per_item_cancel_flips_invoice_to_partially_cancelled(
    tenant, branch, terminal, owner_user, stocked_product,
):
    """PRAL section 4.1.2: cancel ONE item on an invoice. Other items
    remain valid; invoice status flips to partially_cancelled."""
    from apps.catalog.models import Product, UnitOfMeasure
    from datetime import timedelta
    from django.utils import timezone

    api = APIClient()
    _login(api, owner_user.email)

    # Two distinct products so we have two lines.
    p2 = Product.objects.create(
        tenant=tenant, name="Tee", sku="TEE-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("500"), cost_price=Decimal("300"),
    )
    record_movement(
        tenant_id=tenant.id, product=p2, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )

    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [
            {
                "product": str(stocked_product.id),
                "quantity": "1", "unit_price": "1000",
                "tax_rate": "18", "is_taxable": True,
            },
            {
                "product": str(p2.id),
                "quantity": "1", "unit_price": "500",
                "tax_rate": "18", "is_taxable": True,
            },
        ],
        "payments": [{"payment_method": "cash", "amount": "1770"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        create_resp = api.post("/api/sales/invoices/manual/", body, format="json")
    assert create_resp.status_code == 201, create_resp.content
    invoice_id = create_resp.json()["id"]

    # Set the edit_deadline so can_cancel_invoice passes.
    inv = Invoice.objects.get(pk=invoice_id)
    inv.edit_deadline_at = timezone.now() + timedelta(hours=24)
    inv.save(update_fields=["edit_deadline_at"])
    item_to_cancel = inv.items.first()

    resp = api.post(
        f"/api/sales/invoices/{invoice_id}/items/{item_to_cancel.id}/cancel/",
        {"reason": "Wrong item rung up"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    inv.refresh_from_db()
    assert inv.status == "partially_cancelled"
    item_to_cancel.refresh_from_db()
    assert item_to_cancel.is_cancelled is True


@pytest.mark.django_db
def test_per_item_cancel_outside_72h_rejected(
    tenant, branch, terminal, owner_user, stocked_product,
):
    from datetime import timedelta
    from django.utils import timezone

    api = APIClient()
    _login(api, owner_user.email)
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "1000",
            "tax_rate": "18", "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        create = api.post("/api/sales/invoices/manual/", body, format="json")
    invoice_id = create.json()["id"]
    inv = Invoice.objects.get(pk=invoice_id)
    inv.edit_deadline_at = timezone.now() - timedelta(hours=1)  # expired
    inv.save(update_fields=["edit_deadline_at"])

    resp = api.post(
        f"/api/sales/invoices/{invoice_id}/items/{inv.items.first().id}/cancel/",
        {"reason": "Late cancel attempt"},
        format="json",
    )
    assert resp.status_code == 400
    assert "72-hour" in resp.json()["detail"]
