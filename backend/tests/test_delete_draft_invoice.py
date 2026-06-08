"""Deleting an UNSUBMITTED draft invoice (never sent to FBR).

A draft (no fbr_invoice_number, status pending_sync/failed) has nothing on
PRAL's side, so it can be hard-deleted. Stock is restored via an append-only
reversing movement (stock_movements is UPDATE/DELETE-revoked). A fiscalized
invoice (with an FBR number) must be refused — it goes through the FBR cancel
flow instead.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice, Payment, SaleItem
from apps.sales.services import cancellation, checkout
from apps.tenants.models import Branch, Terminal, TenantMembership
from apps.catalog.models import Product, UnitOfMeasure


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MN",
        address="x", city="Karachi", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-del-1",
    )


@pytest.fixture
def cashier(db, tenant):
    from django.contrib.auth import get_user_model
    u = get_user_model().objects.create_user(
        email="c-del@example.com", password="testpass1234", full_name="C",
    )
    TenantMembership.objects.create(tenant=tenant, user=u, role="cashier")
    return u


@pytest.fixture
def stocked_product(db, tenant, branch):
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(
        tenant=tenant, name="Apple", sku="APL-D", uom=uom,
        sale_price=Decimal("100"), cost_price=Decimal("60"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return p


def _make_invoice(tenant, branch, terminal, cashier, product, qty="2"):
    return checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(product.id), "quantity": qty,
                     "unit_price": "100", "tax_rate": "18", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "236"}],
        client_uuid=str(uuid.uuid4()),
    )


@pytest.mark.django_db
def test_delete_draft_removes_invoice_and_restores_stock(
    tenant, branch, terminal, cashier, stocked_product,
):
    inv = _make_invoice(tenant, branch, terminal, cashier, stocked_product, "2")
    inv_id = inv.id
    # Sale dropped stock 100 -> 98
    level = StockLevel.objects.get(product=stocked_product, branch=branch, variant=None)
    assert level.quantity == Decimal("98.0000")

    number = cancellation.delete_draft_invoice(inv, user=cashier)
    assert number == inv.local_invoice_number

    # Soft-deleted: row survives (audit) but deleted_at is set + hidden.
    inv.refresh_from_db()
    assert inv.deleted_at is not None
    # Hidden from the tenant-facing (default) queryset.
    assert not Invoice.objects.filter(id=inv_id, deleted_at__isnull=True).exists()

    # Stock restored 98 -> 100 via a reversing return movement (append-only)
    level.refresh_from_db()
    assert level.quantity == Decimal("100.0000")
    rev = StockMovement.objects.filter(
        reference_id=inv_id, movement_type="return",
    ).first()
    assert rev is not None
    assert rev.quantity == Decimal("2.0000")  # positive = back into stock


@pytest.mark.django_db
def test_delete_draft_allows_failed_status(
    tenant, branch, terminal, cashier, stocked_product,
):
    inv = _make_invoice(tenant, branch, terminal, cashier, stocked_product)
    inv.status = "failed"
    inv.save(update_fields=["status"])
    cancellation.delete_draft_invoice(inv, user=cashier)
    inv.refresh_from_db()
    assert inv.deleted_at is not None


@pytest.mark.django_db
def test_cannot_delete_fiscalized_invoice(
    tenant, branch, terminal, cashier, stocked_product,
):
    from django.core.exceptions import ValidationError
    inv = _make_invoice(tenant, branch, terminal, cashier, stocked_product)
    # Simulate an FBR-accepted invoice.
    inv.fbr_invoice_number = "194444FF1O30420096"
    inv.status = "valid"
    inv.save(update_fields=["fbr_invoice_number", "status"])
    with pytest.raises(ValidationError):
        cancellation.delete_draft_invoice(inv, user=cashier)
    assert Invoice.objects.filter(id=inv.id).exists()  # untouched


@pytest.mark.django_db
def test_delete_draft_endpoint(
    tenant, branch, terminal, cashier, stocked_product,
):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    inv = _make_invoice(tenant, branch, terminal, cashier, stocked_product)
    client = APIClient()
    token = RefreshToken.for_user(cashier)
    token["tenant_id"] = str(tenant.id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    resp = client.delete(f"/api/sales/invoices/{inv.id}/draft/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["deleted"] is True
    # Hidden from the API list/detail (soft-deleted).
    inv.refresh_from_db()
    assert inv.deleted_at is not None
    assert client.get(f"/api/sales/invoices/{inv.id}/").status_code == 404
