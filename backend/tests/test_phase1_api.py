"""Phase 1 API tests — auth-bound CRUD + cross-tenant isolation + CSV import."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, UnitOfMeasure
from apps.tenants.models import Branch, Tenant, TenantMembership

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post(
        "/api/auth/login/",
        {"email": email, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


@pytest.fixture
def second_tenant(db):
    return Tenant.objects.create(
        business_name="Other Shop", ntn="9999999",
        business_type="sole_proprietor", province="PUNJAB",
    )


@pytest.fixture
def other_owner(db, second_tenant):
    u = User.objects.create_user(
        email="other@example.com", password="testpass1234", full_name="Other Owner",
    )
    TenantMembership.objects.create(tenant=second_tenant, user=u, role="owner")
    return u


# ---------------------------------------------------------------------------
# Catalog endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_uoms_listed_for_authenticated_user(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.get("/api/catalog/uoms/")
    assert resp.status_code == 200
    codes = [u["code"] for u in resp.json()]
    assert "PCS" in codes
    assert "KG" in codes


@pytest.mark.django_db
def test_create_product_as_owner(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.post(
        "/api/catalog/products/",
        {
            "name": "Apple",
            "sku": "APL-1",
            "uom": "PCS",
            "sale_price": "100.00",
            "is_taxable": True,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert Product.objects.filter(sku="APL-1").exists()


@pytest.mark.django_db
def test_cashier_cannot_create_product(cashier_user, owner_user):
    api = APIClient()
    _login(api, "cashier@example.com", "testpass1234")
    resp = api.post(
        "/api/catalog/products/",
        {"name": "Apple", "sku": "APL-2", "uom": "PCS", "sale_price": "100.00"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_cross_tenant_product_isolation(owner_user, other_owner, tenant):
    """A user in tenant A cannot see tenant B's products."""
    # Create a product as owner_user (tenant)
    api1 = APIClient()
    _login(api1, "owner@example.com")
    api1.post(
        "/api/catalog/products/",
        {"name": "Tenant1 product", "sku": "T1-1", "uom": "PCS", "sale_price": "100.00"},
        format="json",
    )

    # Login as the other_owner from second_tenant — should NOT see T1-1.
    api2 = APIClient()
    _login(api2, "other@example.com")
    list_resp = api2.get("/api/catalog/products/")
    assert list_resp.status_code == 200
    skus = [p["sku"] for p in list_resp.json()["results"]]
    assert "T1-1" not in skus


@pytest.mark.django_db
def test_product_soft_delete(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.post(
        "/api/catalog/products/",
        {"name": "X", "sku": "X-1", "uom": "PCS", "sale_price": "10.00"},
        format="json",
    )
    pid = resp.json()["id"]
    api.delete(f"/api/catalog/products/{pid}/")
    # Listing default queryset should hide soft-deleted.
    list_resp = api.get("/api/catalog/products/")
    skus = [p["sku"] for p in list_resp.json()["results"]]
    assert "X-1" not in skus


# ---------------------------------------------------------------------------
# CSV import — dry-run + commit
# ---------------------------------------------------------------------------


CSV_OK = (
    "sku,name,uom_code,sale_price,is_taxable\n"
    "C-1,Coke 250ml,PCS,80.00,true\n"
    "C-2,Sprite 250ml,PCS,80.00,true\n"
    "C-3,Fanta 250ml,PCS,75.00,true\n"
).encode("utf-8")


CSV_BAD = (
    "sku,name,uom_code,sale_price\n"
    "B-1,Bad row,XYZ,100.00\n"      # unknown uom
    "B-2,Bad price,PCS,not-a-number\n"
).encode("utf-8")


CSV_BOM = (b"\xef\xbb\xbf"
           b"sku,name,uom_code,sale_price\r\n"
           b"BOM-1,Item with BOM,PCS,55.00\r\n")


@pytest.mark.django_db
def test_csv_import_dry_run(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.post(
        "/api/catalog/products/import/?dry_run=true",
        {"file": ("ok.csv", BytesIO(CSV_OK), "text/csv")},
        format="multipart",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["counts"]["new"] == 3
    assert body["counts"]["updated"] == 0
    assert body["counts"]["errored"] == 0
    # Nothing committed.
    assert Product.objects.filter(sku="C-1").count() == 0


@pytest.mark.django_db
def test_csv_import_commit(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.post(
        "/api/catalog/products/import/",
        {"file": ("ok.csv", BytesIO(CSV_OK), "text/csv")},
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["created"] == 3
    assert Product.objects.filter(sku__in=["C-1", "C-2", "C-3"]).count() == 3


@pytest.mark.django_db
def test_csv_import_dry_run_reports_errors(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.post(
        "/api/catalog/products/import/?dry_run=true",
        {"file": ("bad.csv", BytesIO(CSV_BAD), "text/csv")},
        format="multipart",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["errored"] >= 1
    assert any("uom_code" in e["column"] for e in body["errors"])


@pytest.mark.django_db
def test_csv_import_handles_utf8_bom_and_crlf(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    resp = api.post(
        "/api/catalog/products/import/",
        {"file": ("bom.csv", BytesIO(CSV_BOM), "text/csv")},
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    assert Product.objects.filter(sku="BOM-1").exists()


# ---------------------------------------------------------------------------
# POS sync endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_pos_sync_excludes_cost_price(owner_user):
    api = APIClient()
    _login(api, "owner@example.com")
    api.post(
        "/api/catalog/products/",
        {
            "name": "Pos test", "sku": "POS-1", "uom": "PCS",
            "cost_price": "50.00", "sale_price": "100.00",
        },
        format="json",
    )
    sync = api.get("/api/catalog/sync/")
    assert sync.status_code == 200, sync.content
    products = sync.json()["products"]
    assert len(products) == 1
    assert "cost_price" not in products[0]


# ---------------------------------------------------------------------------
# Inventory adjustments + stock levels
# ---------------------------------------------------------------------------


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Defence", code="DHA",
        address="…", city="Karachi", province="SINDH",
    )


@pytest.mark.django_db
def test_owner_can_post_adjustment(owner_user, branch):
    api = APIClient()
    _login(api, "owner@example.com")

    p_resp = api.post(
        "/api/catalog/products/",
        {"name": "Adj test", "sku": "ADJ-1", "uom": "PCS", "sale_price": "1.00"},
        format="json",
    )
    pid = p_resp.json()["id"]

    resp = api.post(
        "/api/inventory/adjustments/",
        {
            "branch": str(branch.id),
            "product": pid,
            "quantity": "25",
            "movement_type": "opening_balance",
            "reason": "initial seeding",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content

    levels = api.get(f"/api/inventory/stock-levels/?branch={branch.id}").json()
    rows = levels["results"] if "results" in levels else levels
    qtys = {r["product"]: r["quantity"] for r in rows}
    assert qtys[pid] == "25.0000"
