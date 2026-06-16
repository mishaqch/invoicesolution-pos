"""Product SKU uniqueness — clean 400 on live dupe, reuse after soft-delete.

Regression: creating a product whose SKU collided with an existing row (incl.
soft-deleted ones, because the unique constraint had no deleted_at condition)
crashed with HTTP 500 (IntegrityError). Now: live dupe → 400; a soft-deleted
product's SKU is free to reuse → 201.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import HsCode, Product, UnitOfMeasure


def _auth(client, user, tenant):
    token = RefreshToken.for_user(user)
    token["tenant_id"] = str(tenant.id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


def _payload(sku):
    uom = UnitOfMeasure.objects.get(code="PCS")
    hs = HsCode.objects.first()
    return {
        "name": "Widget", "sku": sku, "uom": uom.code,
        "hs_code": hs.code if hs else None,
        "sale_price": "100", "cost_price": "50", "is_taxable": True,
    }


@pytest.fixture
def hs_code(db):
    return HsCode.objects.create(code="8711.6020", description="Test motorcycle")


def test_duplicate_live_sku_returns_400_not_500(db, tenant, owner_user, hs_code):
    Product.objects.create(
        tenant=tenant, name="X", sku="DUP-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("100"), hs_code=hs_code,
    )
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.post("/api/catalog/products/", _payload("DUP-1"), format="json")
    assert resp.status_code == 400, resp.content
    assert "sku" in resp.json()


def test_reuse_soft_deleted_sku_succeeds(db, tenant, owner_user, hs_code):
    from django.utils import timezone
    p = Product.objects.create(
        tenant=tenant, name="Old", sku="REUSE-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("100"), hs_code=hs_code,
    )
    # Soft-delete it (what the DELETE endpoint does).
    p.deleted_at = timezone.now()
    p.is_active = False
    p.save(update_fields=["deleted_at", "is_active"])

    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.post("/api/catalog/products/", _payload("REUSE-1"), format="json")
    assert resp.status_code == 201, resp.content
    # Both rows exist: one deleted, one live, same SKU.
    assert Product.objects.filter(tenant=tenant, sku="REUSE-1").count() == 2
    assert Product.objects.filter(tenant=tenant, sku="REUSE-1", deleted_at__isnull=True).count() == 1
