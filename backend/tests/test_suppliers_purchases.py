"""Suppliers + goods-receipt (GRN) posting.

Posting a GRN must:
  - create a ProductBatch for batch-tracked lines (with expiry + supplier),
  - record a `purchase` stock movement,
  - bump the aggregate StockLevel AND the batch's current_quantity,
  - flip the GRN to 'posted' and reject a second post.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import Product, ProductBatch, UnitOfMeasure
from apps.inventory.models import StockLevel, StockMovement
from apps.purchases.models import GoodsReceipt, GoodsReceiptItem
from apps.purchases.services import post_receipt
from apps.suppliers.models import Supplier
from apps.tenants.models import Branch


def _auth(client, user, tenant):
    token = RefreshToken.for_user(user)
    token["tenant_id"] = str(tenant.id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MN", address="x", city="Karachi", province="SINDH",
    )


@pytest.fixture
def supplier(db, tenant):
    return Supplier.objects.create(tenant=tenant, name="Acme Pharma Distributors")


@pytest.fixture
def batch_product(db, tenant):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="Augmentin 625mg", sku="AUG-625", uom=uom,
        sale_price=Decimal("450"), is_batch_tracked=True,
    )


def test_supplier_crud_is_tenant_scoped(db, tenant, owner_user, supplier):
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get("/api/suppliers/")
    assert resp.status_code == 200, resp.content
    names = {s["name"] for s in resp.json()["results"]}
    assert "Acme Pharma Distributors" in names


def test_post_receipt_creates_batch_and_stock(db, tenant, owner_user, branch, supplier, batch_product):
    grn = GoodsReceipt.objects.create(
        tenant=tenant, supplier=supplier, branch=branch,
        reference="INV-9001", received_date=date(2026, 6, 1),
    )
    GoodsReceiptItem.objects.create(
        receipt=grn, product=batch_product, quantity=Decimal("100"),
        cost_price=Decimal("300"), batch_number="AUG-B1",
        expiry_date=date(2027, 6, 1),
    )

    post_receipt(grn, user=owner_user)
    grn.refresh_from_db()
    assert grn.status == "posted"
    assert grn.posted_at is not None

    # A batch was created with the GRN's expiry + supplier.
    batch = ProductBatch.objects.get(product=batch_product, batch_number="AUG-B1")
    assert batch.current_quantity == Decimal("100")
    assert batch.expiry_date == date(2027, 6, 1)
    assert batch.supplier_id == supplier.id

    # A purchase movement was recorded against the batch.
    mv = StockMovement.objects.get(batch=batch, movement_type="purchase")
    assert mv.quantity == Decimal("100")

    # Aggregate stock level bumped.
    level = StockLevel.objects.get(product=batch_product, branch=branch, variant=None)
    assert level.quantity == Decimal("100")


def test_double_post_is_rejected(db, tenant, owner_user, branch, supplier, batch_product):
    from django.core.exceptions import ValidationError

    grn = GoodsReceipt.objects.create(
        tenant=tenant, supplier=supplier, branch=branch, received_date=date(2026, 6, 1),
    )
    GoodsReceiptItem.objects.create(
        receipt=grn, product=batch_product, quantity=Decimal("10"),
        batch_number="B-1", expiry_date=date(2027, 1, 1),
    )
    post_receipt(grn, user=owner_user)
    with pytest.raises(ValidationError):
        post_receipt(grn, user=owner_user)


def test_post_via_api_endpoint(db, tenant, owner_user, branch, supplier, batch_product):
    client = APIClient()
    _auth(client, owner_user, tenant)

    create = client.post(
        "/api/purchases/receipts/",
        {
            "supplier": str(supplier.id),
            "branch": str(branch.id),
            "reference": "INV-2",
            "received_date": "2026-06-02",
            "items": [
                {
                    "product": str(batch_product.id),
                    "quantity": "50",
                    "cost_price": "300.0000",
                    "batch_number": "API-B1",
                    "expiry_date": "2027-12-01",
                },
            ],
        },
        format="json",
    )
    assert create.status_code == 201, create.content
    grn_id = create.json()["id"]

    posted = client.post(f"/api/purchases/receipts/{grn_id}/post/")
    assert posted.status_code == 200, posted.content
    assert posted.json()["status"] == "posted"

    batch = ProductBatch.objects.get(batch_number="API-B1")
    assert batch.current_quantity == Decimal("50")
