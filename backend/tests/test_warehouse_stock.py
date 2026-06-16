"""Multi-warehouse stock for Digital-Invoicing tenants.

Covers the backward-compat guarantee (POS / no-warehouse path unchanged), the
warehouse-keyed stock path, warehouse CRUD + module gating, and the adjustment
(opening-balance) flow per warehouse.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockLevel, StockMovement, Warehouse
from apps.inventory.services.movements import record_movement
from apps.sales.services import checkout
from apps.tenants.models import Branch, Terminal


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
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-wh-1",
    )


@pytest.fixture
def product(db, tenant):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="Widget", sku="W-1", uom=uom,
        sale_price=Decimal("100"), is_taxable=False,
    )


def _sale(tenant, branch, terminal, cashier, product, *, warehouse=None, qty="1"):
    return checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None, warehouse=warehouse,
        cart_lines=[{"product": str(product.id), "quantity": qty, "unit_price": "100",
                     "tax_rate": "0", "is_taxable": False}],
        payments=[{"payment_method": "cash", "amount": str(Decimal("100") * Decimal(qty))}],
        client_uuid=str(uuid.uuid4()),
    )


def _enable_module(tenant, *keys):
    mods = list(tenant.modules_enabled or [])
    for k in keys:
        if k not in mods:
            mods.append(k)
    tenant.modules_enabled = mods
    tenant.save(update_fields=["modules_enabled"])


# ---------------------------------------------------------------------------
# Backward-compat: the no-warehouse path is byte-for-byte unchanged (POS).
# ---------------------------------------------------------------------------


def test_record_movement_without_warehouse_is_branch_keyed(db, tenant, branch, product):
    record_movement(
        tenant_id=tenant.id, product=product, branch=branch,
        movement_type="opening_balance", quantity=Decimal("10"),
    )
    level = StockLevel.objects.get(product=product, branch=branch, warehouse__isnull=True)
    assert level.quantity == Decimal("10")
    assert level.warehouse_id is None
    mv = StockMovement.objects.get(product=product)
    assert mv.warehouse_id is None  # POS movements never carry a warehouse


def test_warehouse_and_branch_levels_coexist(db, tenant, branch, product):
    """A NULL-warehouse (POS) level and a warehouse-keyed (DI) level for the
    same (product, branch) can coexist without violating either constraint."""
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="Godown A", code="GA")
    record_movement(
        tenant_id=tenant.id, product=product, branch=branch,
        movement_type="opening_balance", quantity=Decimal("5"),
    )  # branch-keyed
    record_movement(
        tenant_id=tenant.id, product=product, branch=branch, warehouse=wh,
        movement_type="opening_balance", quantity=Decimal("8"),
    )  # warehouse-keyed
    assert StockLevel.objects.filter(product=product, branch=branch).count() == 2
    assert StockLevel.objects.get(warehouse__isnull=True).quantity == Decimal("5")
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("8")


def test_two_warehouses_track_stock_independently(db, tenant, branch, product):
    a = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    b = Warehouse.objects.create(tenant=tenant, branch=branch, name="B", code="B")
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=a,
                    movement_type="opening_balance", quantity=Decimal("3"))
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=b,
                    movement_type="opening_balance", quantity=Decimal("7"))
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=a,
                    movement_type="sale", quantity=Decimal("-1"))
    assert StockLevel.objects.get(warehouse=a).quantity == Decimal("2")
    assert StockLevel.objects.get(warehouse=b).quantity == Decimal("7")


# ---------------------------------------------------------------------------
# Warehouse CRUD API + module gating.
# ---------------------------------------------------------------------------


def test_warehouse_crud_for_di_tenant(db, tenant, branch, owner_user):
    _enable_module(tenant, "warehouses")
    client = APIClient()
    _auth(client, owner_user, tenant)

    resp = client.post("/api/inventory/warehouses/", {
        "branch": str(branch.id), "name": "Lahore Godown", "code": "LHR", "is_default": True,
    }, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["branch_name"] == "Main"
    assert body["is_default"] is True

    # Second default in the same branch flips the first off.
    resp2 = client.post("/api/inventory/warehouses/", {
        "branch": str(branch.id), "name": "Cold Store", "code": "CS", "is_default": True,
    }, format="json")
    assert resp2.status_code == 201
    assert Warehouse.objects.filter(branch=branch, is_default=True).count() == 1


def test_warehouse_endpoint_forbidden_without_module(db, tenant, branch, owner_user):
    # Simulate a POS tenant: strip the warehouses module.
    tenant.modules_enabled = [m for m in (tenant.modules_enabled or []) if m != "warehouses"]
    tenant.save(update_fields=["modules_enabled"])
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get("/api/inventory/warehouses/")
    assert resp.status_code == 403


def test_cannot_delete_warehouse_with_stock(db, tenant, branch, product, owner_user):
    _enable_module(tenant, "warehouses")
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=wh,
                    movement_type="opening_balance", quantity=Decimal("5"))
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.delete(f"/api/inventory/warehouses/{wh.id}/")
    assert resp.status_code == 400


def test_opening_balance_adjustment_per_warehouse(db, tenant, branch, product, owner_user):
    _enable_module(tenant, "warehouses")
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.post("/api/inventory/adjustments/", {
        "branch": str(branch.id), "warehouse": str(wh.id), "product": str(product.id),
        "quantity": "25", "reason": "Opening", "movement_type": "opening_balance",
    }, format="json")
    assert resp.status_code == 201, resp.content
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("25")

    # Stock-levels endpoint filtered by warehouse returns it.
    levels = client.get(f"/api/inventory/stock-levels/?warehouse={wh.id}").json()
    assert levels["results"][0]["quantity"] == "25.0000"
    assert levels["results"][0]["warehouse_name"] == "A"


def test_adjustment_rejects_warehouse_from_other_branch(db, tenant, owner_user, product):
    _enable_module(tenant, "warehouses")
    b1 = Branch.objects.create(tenant=tenant, name="B1", code="B1", address="x", city="K", province="SINDH")
    b2 = Branch.objects.create(tenant=tenant, name="B2", code="B2", address="x", city="K", province="SINDH")
    wh2 = Warehouse.objects.create(tenant=tenant, branch=b2, name="W2", code="W2")
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.post("/api/inventory/adjustments/", {
        "branch": str(b1.id), "warehouse": str(wh2.id), "product": str(product.id),
        "quantity": "5", "reason": "x", "movement_type": "opening_balance",
    }, format="json")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Sale deduction + reversal against a warehouse.
# ---------------------------------------------------------------------------


def test_sale_deducts_from_chosen_warehouse(db, tenant, branch, terminal, owner_user, product):
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=wh,
                    movement_type="opening_balance", quantity=Decimal("10"))

    inv = _sale(tenant, branch, terminal, owner_user, product, warehouse=wh, qty="3")
    assert inv.warehouse_id == wh.id
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("7")
    # No branch-keyed (warehouse-NULL) level was created.
    assert not StockLevel.objects.filter(product=product, warehouse__isnull=True).exists()


def test_cancel_returns_stock_to_same_warehouse(db, tenant, branch, terminal, owner_user, product):
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=wh,
                    movement_type="opening_balance", quantity=Decimal("10"))
    inv = _sale(tenant, branch, terminal, owner_user, product, warehouse=wh, qty="4")
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("6")

    # Reverse the sale movements directly (the FBR-state guard in cancel_invoice
    # is out of scope here — we assert the stock-reversal warehouse routing).
    for item in inv.items.all():
        record_movement(
            tenant_id=tenant.id, product=item.product, branch=inv.branch,
            warehouse=inv.warehouse, movement_type="return", quantity=item.quantity,
        )
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("10")


def test_pos_sale_unchanged_no_warehouse(db, tenant, branch, terminal, owner_user, product):
    """POS proof: a sale with no warehouse keeps branch-keyed stock + NULL
    warehouse on both the level and the movement — byte-for-byte as before."""
    record_movement(tenant_id=tenant.id, product=product, branch=branch,
                    movement_type="opening_balance", quantity=Decimal("10"))
    inv = _sale(tenant, branch, terminal, owner_user, product, warehouse=None, qty="2")

    assert inv.warehouse_id is None
    level = StockLevel.objects.get(product=product, branch=branch, warehouse__isnull=True)
    assert level.quantity == Decimal("8")
    # The sale movement carries no warehouse.
    sale_mv = StockMovement.objects.get(movement_type="sale", reference_id=inv.id)
    assert sale_mv.warehouse_id is None
    # No warehouse-keyed level leaked into existence.
    assert not StockLevel.objects.filter(warehouse__isnull=False).exists()


# ---------------------------------------------------------------------------
# New: warehouse city/address + stock FBR fields (HS/UoM/sale_type).
# ---------------------------------------------------------------------------


def test_warehouse_city_address_roundtrip(db, tenant, branch, owner_user):
    _enable_module(tenant, "warehouses")
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.post("/api/inventory/warehouses/", {
        "branch": str(branch.id), "name": "Lahore Godown", "code": "LHR",
        "city": "Lahore", "address": "Band Road",
    }, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["city"] == "Lahore"
    assert body["address"] == "Band Road"


def test_stock_level_exposes_product_fbr_fields(db, tenant, branch, owner_user, product):
    _enable_module(tenant, "warehouses")
    # Give the product FBR metadata.
    product.hs_code_id = None  # product fixture has no hs by default
    product.sale_type = "Goods at Reduced Rate"
    product.save(update_fields=["sale_type"])
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    record_movement(tenant_id=tenant.id, product=product, branch=branch, warehouse=wh,
                    movement_type="opening_balance", quantity=Decimal("5"))
    client = APIClient()
    _auth(client, owner_user, tenant)
    rows = client.get(f"/api/inventory/stock-levels/?warehouse={wh.id}").json()["results"]
    assert rows, "expected a stock row"
    r = rows[0]
    # FBR fields embedded on the stock row.
    assert r["product_name"] == product.name
    assert r["product_sku"] == product.sku
    assert r["uom"] == product.uom_id
    assert r["sale_type"] == "Goods at Reduced Rate"
    assert "hs_code" in r


# ---------------------------------------------------------------------------
# Opening balance is an ABSOLUTE set (idempotent) — not a blind add.
# ---------------------------------------------------------------------------


def test_opening_balance_is_idempotent_set_not_add(db, tenant, branch, owner_user, product):
    _enable_module(tenant, "warehouses")
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    client = APIClient()
    _auth(client, owner_user, tenant)

    def opening(qty):
        return client.post("/api/inventory/adjustments/", {
            "branch": str(branch.id), "warehouse": str(wh.id), "product": str(product.id),
            "quantity": qty, "reason": "Opening", "movement_type": "opening_balance",
        }, format="json")

    # First opening balance → 100.
    assert opening("100").status_code == 201
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("100")

    # Re-entering the SAME opening balance must NOT double it (was the footgun).
    r2 = opening("100")
    assert r2.status_code in (200, 201)
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("100")

    # Entering a NEW opening balance SETS to the new value (correct downward too).
    assert opening("60").status_code == 201
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("60")


def test_opening_balance_then_sale_then_set_to_zero(db, tenant, branch, terminal, owner_user, product):
    """Edit-to-zero (the stock 'remove' action) works via opening_balance=0."""
    _enable_module(tenant, "warehouses")
    wh = Warehouse.objects.create(tenant=tenant, branch=branch, name="A", code="A")
    client = APIClient()
    _auth(client, owner_user, tenant)
    client.post("/api/inventory/adjustments/", {
        "branch": str(branch.id), "warehouse": str(wh.id), "product": str(product.id),
        "quantity": "50", "reason": "Opening", "movement_type": "opening_balance",
    }, format="json")
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("50")
    # Remove → set to 0.
    client.post("/api/inventory/adjustments/", {
        "branch": str(branch.id), "warehouse": str(wh.id), "product": str(product.id),
        "quantity": "0", "reason": "Removed", "movement_type": "opening_balance",
    }, format="json")
    assert StockLevel.objects.get(warehouse=wh).quantity == Decimal("0")
