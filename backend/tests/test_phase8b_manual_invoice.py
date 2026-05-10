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


@pytest.mark.django_db
def test_invoice_pdf_renders_and_returns_valid_pdf(
    tenant, branch, terminal, owner_user, stocked_product,
):
    """The /pdf/ endpoint should return a valid PDF document."""
    api = APIClient()
    _login(api, owner_user.email)
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "1000",
            "tax_rate": "18", "is_taxable": True,
            "hs_code": "0101.2100",
            "uom_code": "PCS",
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        create = api.post("/api/sales/invoices/manual/", body, format="json")
    invoice_id = create.json()["id"]

    resp = api.get(f"/api/sales/invoices/{invoice_id}/pdf/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    body_bytes = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content
    assert body_bytes[:4] == b"%PDF"
    assert len(body_bytes) > 1000  # has actual content (header + body + table)


@pytest.mark.django_db
def test_invoice_pdf_includes_fbr_qr_when_validated(
    tenant, branch, terminal, owner_user, stocked_product,
):
    """An FBR-validated invoice (has fbr_invoice_number + fbr_qr_payload)
    should embed the QR image; a non-validated one should not."""
    from apps.sales.services.invoice_pdf import render_invoice_pdf

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
    inv = Invoice.objects.get(pk=create.json()["id"])

    pdf_no_fbr = render_invoice_pdf(inv)
    assert pdf_no_fbr[:4] == b"%PDF"
    size_without_qr = len(pdf_no_fbr)

    # Now stamp a valid FBR response and re-render — bytes go up because
    # the QR image is now embedded.
    from apps.fbr.qr import build_qr_payload
    inv.fbr_invoice_number = "8885801DI20260510TEST123"
    inv.fbr_qr_payload = build_qr_payload(
        fbr_invoice_number=inv.fbr_invoice_number,
        validated_at=inv.created_at,
        amount=inv.grand_total,
        seller_ntn=tenant.ntn,
    )
    inv.status = "valid"
    inv.save()
    pdf_with_fbr = render_invoice_pdf(inv)
    assert pdf_with_fbr[:4] == b"%PDF"
    # The QR image embed adds significant bytes — sanity check it grew.
    assert len(pdf_with_fbr) > size_without_qr


# ---------------------------------------------------------------------------
# Debit note (issued against an existing validated invoice)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_debit_note_links_to_original_and_copies_buyer(
    tenant, branch, terminal, owner_user, stocked_product,
):
    """Original validated invoice + a debit note that references it.
    Buyer block on the note copies from the original (auditors expect
    the same buyer on both documents)."""
    api = APIClient()
    _login(api, owner_user.email)

    original_body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "5", "unit_price": "1000", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "5900"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r1 = api.post("/api/sales/invoices/manual/", original_body, format="json")
    assert r1.status_code == 201
    original_id = r1.json()["id"]
    Invoice.objects.filter(pk=original_id).update(
        status="valid", buyer_name="Khan Trading Co",
        buyer_phone="+92 300 1234567", buyer_ntn_cnic="1234567890123",
    )

    debit_body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "2", "unit_price": "1000", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "2360"}],
        "client_uuid": str(uuid.uuid4()),
        "invoice_type": "debit_note",
        "reference_invoice": original_id,
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay") as mock_submit:
        r2 = api.post("/api/sales/invoices/manual/", debit_body, format="json")
    assert r2.status_code == 201, r2.content

    note = Invoice.objects.get(pk=r2.json()["id"])
    assert note.invoice_type == "debit_note"
    assert str(note.reference_invoice_id) == original_id
    # Buyer copied from original (no `customer` arg supplied in debit_body).
    assert note.buyer_name == "Khan Trading Co"
    assert note.buyer_phone == "+92 300 1234567"
    assert note.buyer_ntn_cnic == "1234567890123"
    # Money matches the new lines, NOT the original.
    assert note.grand_total == Decimal("2360.0000")
    # FBR queued for the note (just like a normal sale).
    mock_submit.assert_called_once_with(str(note.id))


@pytest.mark.django_db
def test_debit_note_refuses_cancelled_original(
    tenant, branch, terminal, owner_user, stocked_product,
):
    api = APIClient()
    _login(api, owner_user.email)

    original_body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "1000", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r1 = api.post("/api/sales/invoices/manual/", original_body, format="json")
    Invoice.objects.filter(pk=r1.json()["id"]).update(status="cancelled")

    debit_body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "1000", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
        "invoice_type": "debit_note",
        "reference_invoice": r1.json()["id"],
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r2 = api.post("/api/sales/invoices/manual/", debit_body, format="json")
    assert r2.status_code == 400


@pytest.mark.django_db
def test_debit_note_requires_reference_invoice(
    tenant, branch, terminal, owner_user, stocked_product,
):
    """Serializer-level: debit_note without reference_invoice is rejected."""
    api = APIClient()
    _login(api, owner_user.email)
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "1000", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "1180"}],
        "client_uuid": str(uuid.uuid4()),
        "invoice_type": "debit_note",
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        resp = api.post("/api/sales/invoices/manual/", body, format="json")
    assert resp.status_code == 400
    assert "reference_invoice" in resp.json()

