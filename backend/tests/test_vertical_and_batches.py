"""Vertical (grocery vs pharmacy) + pharmacy batch management.

Covers:
  - Tenant.vertical defaults to 'grocery' and surfaces in /api/me/modules/.
  - Creating a ProductBatch via the API sets current_quantity = initial_quantity
    AND records an opening_balance StockMovement so the aggregate StockLevel
    stays consistent (record_movement is the only sanctioned stock mutation).
  - Batch listing is filterable by ?product= and tenant-isolated.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import Product, ProductBatch, UnitOfMeasure
from apps.inventory.models import StockLevel, StockMovement
from apps.tenants.models import Branch, Tenant, TenantMembership


def _auth(client, user, tenant):
    token = RefreshToken.for_user(user)
    token["tenant_id"] = str(tenant.id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MN",
        address="x", city="Karachi", province="SINDH",
    )


@pytest.fixture
def product(db, tenant):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="Panadol 500mg", sku="PAN-500", uom=uom,
        sale_price=Decimal("20"), cost_price=Decimal("12"),
        is_batch_tracked=True,
    )


# ---------------------------------------------------------------------------
# Vertical flag
# ---------------------------------------------------------------------------


def test_default_vertical_is_grocery(tenant):
    assert tenant.vertical == "grocery"


def test_me_modules_exposes_vertical(db, tenant, owner_user):
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get("/api/me/modules/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["vertical"] == "grocery"


def test_me_modules_reports_pharmacy(db, owner_user):
    t = Tenant.objects.create(
        business_name="City Pharmacy", ntn="9991111-0",
        business_type="sole_proprietor", province="PUNJAB",
        vertical="pharmacy",
    )
    TenantMembership.objects.create(tenant=t, user=owner_user, role="owner")
    client = APIClient()
    _auth(client, owner_user, t)
    resp = client.get("/api/me/modules/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["vertical"] == "pharmacy"


# ---------------------------------------------------------------------------
# Batch management
# ---------------------------------------------------------------------------


def test_create_batch_records_opening_movement_and_stock(db, tenant, owner_user, branch, product):
    client = APIClient()
    _auth(client, owner_user, tenant)

    resp = client.post(
        "/api/catalog/batches/",
        {
            "product": str(product.id),
            "batch_number": "B-001",
            "expiry_date": "2027-12-31",
            "cost_price": "12.0000",
            "initial_quantity": "50",
            "branch": str(branch.id),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()

    # current_quantity derived from initial_quantity (not user-supplied).
    assert Decimal(body["current_quantity"]) == Decimal("50")
    assert body["batch_number"] == "B-001"

    batch = ProductBatch.objects.get(pk=body["id"])
    assert batch.current_quantity == Decimal("50")

    # An opening_balance movement was appended, tagged to the batch.
    mv = StockMovement.objects.get(batch=batch)
    assert mv.movement_type == "opening_balance"
    assert mv.quantity == Decimal("50")

    # And the aggregate stock level bumped by the same amount.
    level = StockLevel.objects.get(product=product, branch=branch, variant=None)
    assert level.quantity == Decimal("50")


def test_batch_list_filters_by_product(db, tenant, owner_user, branch, product):
    uom = UnitOfMeasure.objects.get(code="PCS")
    other = Product.objects.create(
        tenant=tenant, name="Disprin", sku="DIS-1", uom=uom,
        sale_price=Decimal("10"), is_batch_tracked=True,
    )
    ProductBatch.objects.create(
        product=product, batch_number="P-1", initial_quantity=Decimal("5"),
        current_quantity=Decimal("5"), branch=branch,
    )
    ProductBatch.objects.create(
        product=other, batch_number="O-1", initial_quantity=Decimal("9"),
        current_quantity=Decimal("9"), branch=branch,
    )

    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get(f"/api/catalog/batches/?product={product.id}")
    assert resp.status_code == 200, resp.content
    results = resp.json()["results"]
    assert {r["batch_number"] for r in results} == {"P-1"}


def test_batch_list_is_tenant_isolated(db, tenant, owner_user, branch, product):
    # A batch belonging to ANOTHER tenant must never appear.
    other_tenant = Tenant.objects.create(
        business_name="Other", ntn="5550000-0",
        business_type="sole_proprietor", province="SINDH",
    )
    other_branch = Branch.objects.create(
        tenant=other_tenant, name="O", code="OO",
        address="y", city="Lahore", province="PUNJAB",
    )
    uom = UnitOfMeasure.objects.get(code="PCS")
    other_product = Product.objects.create(
        tenant=other_tenant, name="Secret", sku="SEC-1", uom=uom,
        sale_price=Decimal("1"), is_batch_tracked=True,
    )
    ProductBatch.objects.create(
        product=other_product, batch_number="HIDDEN", initial_quantity=Decimal("1"),
        current_quantity=Decimal("1"), branch=other_branch,
    )

    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get("/api/catalog/batches/")
    assert resp.status_code == 200, resp.content
    numbers = {r["batch_number"] for r in resp.json()["results"]}
    assert "HIDDEN" not in numbers


# ---------------------------------------------------------------------------
# Expiry list
# ---------------------------------------------------------------------------


def _mk_batch(product, branch, batch_number, expiry, qty="10"):
    from datetime import date

    return ProductBatch.objects.create(
        product=product, branch=branch, batch_number=batch_number,
        expiry_date=date.fromisoformat(expiry),
        initial_quantity=Decimal(qty), current_quantity=Decimal(qty),
    )


def test_expiry_buckets_and_window(db, tenant, owner_user, branch, product):
    from datetime import timedelta

    from django.utils import timezone

    today = timezone.localdate()
    _mk_batch(product, branch, "EXP", (today - timedelta(days=5)).isoformat())
    _mk_batch(product, branch, "SOON", (today + timedelta(days=10)).isoformat())
    _mk_batch(product, branch, "UPCOMING", (today + timedelta(days=60)).isoformat())
    # Outside the 90d window — must NOT appear.
    _mk_batch(product, branch, "FAR", (today + timedelta(days=200)).isoformat())
    # In-window but zero stock — must NOT appear.
    _mk_batch(product, branch, "EMPTY", (today + timedelta(days=5)).isoformat(), qty="0")

    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get("/api/inventory/expiry/?within=90")
    assert resp.status_code == 200, resp.content
    rows = {r["batch_number"]: r for r in resp.json()["results"]}

    assert set(rows) == {"EXP", "SOON", "UPCOMING"}
    assert rows["EXP"]["bucket"] == "expired"
    assert rows["SOON"]["bucket"] == "soon"
    assert rows["UPCOMING"]["bucket"] == "upcoming"
    # Soonest-expiry first.
    order = [r["batch_number"] for r in resp.json()["results"]]
    assert order == ["EXP", "SOON", "UPCOMING"]


# ---------------------------------------------------------------------------
# FEFO: selling against a batch depletes that batch's current_quantity
# ---------------------------------------------------------------------------


def test_sale_against_batch_decrements_batch_quantity(db, tenant, branch, product, owner_user):
    """A checkout that names a batch must reduce that batch's current_quantity
    (so FEFO advances to the next lot) AND the aggregate stock level."""
    import uuid

    from apps.sales.services import checkout
    from apps.tenants.models import Terminal

    terminal = Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-fefo-1",
    )
    # Batch starts at 50 (created directly with that quantity). Also seed an
    # aggregate StockLevel so the sale has stock to draw down.
    batch = _mk_batch(product, branch, "B-FEFO", "2027-01-01", qty="50")
    from apps.inventory.models import StockLevel
    StockLevel.objects.create(
        tenant_id=tenant.id, product=product, branch=branch, quantity=Decimal("50"),
    )

    checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{
            "product": str(product.id),
            "batch": str(batch.id),
            "quantity": "3",
            "unit_price": "20",
            "tax_rate": "0",
            "is_taxable": False,
        }],
        payments=[{"payment_method": "cash", "amount": "60"}],
        client_uuid=uuid.uuid4(),
    )

    batch.refresh_from_db()
    assert batch.current_quantity == Decimal("47"), "batch counter must drop by qty sold"
