"""Restaurant vertical — orders-as-held-invoices, modifiers, kitchen, floor.

Covers:
  - restaurant vertical surfaces in /api/me/modules/ + the `restaurant` module
  - a checkout carrying order_type/table/modifiers snapshots them onto the
    invoice + sale items (modifier price already folded into unit_price)
  - send-to-kitchen flips order_status + flags unsent lines + is incremental
  - floor + KDS endpoints aggregate open orders
  - tables / modifier-groups are tenant-isolated
  - REGRESSION: a plain (non-restaurant) checkout is byte-identical — no
    restaurant fields leak onto a grocery invoice.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import Product, UnitOfMeasure
from apps.restaurant.models import Modifier, ModifierGroup, Table
from apps.sales.models import Invoice, SaleItem
from apps.sales.services import checkout
from apps.tenants.models import Branch, Tenant, TenantMembership


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
    from apps.tenants.models import Terminal
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-resto-1",
    )


@pytest.fixture
def burger(db, tenant):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="Zinger Burger", sku="ZB-1", uom=uom,
        sale_price=Decimal("450"), is_taxable=False,
    )


# ---------------------------------------------------------------------------
# Vertical + module
# ---------------------------------------------------------------------------


def test_restaurant_vertical_in_modules(db, owner_user):
    t = Tenant.objects.create(
        business_name="Burger Lab", ntn="7001234-0",
        business_type="sole_proprietor", province="PUNJAB", vertical="restaurant",
    )
    TenantMembership.objects.create(tenant=t, user=owner_user, role="owner")
    client = APIClient()
    _auth(client, owner_user, t)
    body = client.get("/api/me/modules/").json()
    assert body["vertical"] == "restaurant"
    assert "restaurant" in body["enabled"]


# ---------------------------------------------------------------------------
# Checkout with modifiers + order fields
# ---------------------------------------------------------------------------


def test_order_checkout_snapshots_modifiers_and_table(db, tenant, branch, terminal, owner_user, burger):
    table = Table.objects.create(tenant=tenant, branch=branch, name="T5", seats=4)
    # Burger 450 + "Extra cheese" 50 = 500 unit price (caller folds the delta in).
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{
            "product": str(burger.id),
            "quantity": "2",
            "unit_price": "500",
            "tax_rate": "0",
            "is_taxable": False,
            "modifiers": [{"name": "Extra cheese", "price": "50.0000"}],
            "item_note": "no mayo",
            "course": 1,
        }],
        payments=[{"payment_method": "cash", "amount": "1000"}],
        client_uuid=uuid.uuid4(),
        order_type="dine_in", table_id=str(table.id), covers=2,
    )
    assert inv.order_type == "dine_in"
    assert str(inv.table_id) == str(table.id)
    assert inv.covers == 2
    assert inv.order_status == "open"
    assert inv.grand_total == Decimal("1000.0000")  # 2 x 500

    item = inv.items.get()
    assert item.modifiers == [{"name": "Extra cheese", "price": "50.0000"}]
    assert item.item_note == "no mayo"
    assert item.course == 1


def test_send_to_kitchen_is_incremental(db, tenant, branch, terminal, owner_user, burger):
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(burger.id), "quantity": "1", "unit_price": "450",
                     "tax_rate": "0", "is_taxable": False}],
        payments=[{"payment_method": "cash", "amount": "450"}],
        client_uuid=uuid.uuid4(), order_type="dine_in",
    )
    from apps.restaurant.services import send_to_kitchen
    send_to_kitchen(inv, user=owner_user)
    inv.refresh_from_db()
    assert inv.order_status == "sent_to_kitchen"
    assert inv.kitchen_sent_at is not None
    assert inv.items.filter(sent_to_kitchen=True).count() == 1


def test_floor_and_kds_endpoints(db, tenant, branch, terminal, owner_user, burger):
    table = Table.objects.create(tenant=tenant, branch=branch, name="T1", seats=2)
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(burger.id), "quantity": "1", "unit_price": "450",
                     "tax_rate": "0", "is_taxable": False}],
        payments=[{"payment_method": "cash", "amount": "450"}],
        client_uuid=uuid.uuid4(), order_type="dine_in", table_id=str(table.id),
    )
    # Make it an OPEN order (held) and fire it.
    inv.is_held = True
    inv.save(update_fields=["is_held"])
    from apps.restaurant.services import send_to_kitchen
    send_to_kitchen(inv, user=owner_user)

    client = APIClient()
    _auth(client, owner_user, tenant)

    floor = client.get("/api/restaurant/floor/").json()
    t1 = next(t for t in floor["tables"] if t["name"] == "T1")
    assert t1["order"] is not None and t1["order"]["order_status"] == "sent_to_kitchen"

    kds = client.get("/api/restaurant/kds/").json()
    assert len(kds["orders"]) == 1


def test_tables_are_tenant_isolated(db, tenant, branch, owner_user):
    other = Tenant.objects.create(
        business_name="Other Cafe", ntn="8001111-0",
        business_type="sole_proprietor", province="SINDH", vertical="restaurant",
    )
    ob = Branch.objects.create(tenant=other, name="O", code="OO", address="y", city="Lahore", province="PUNJAB")
    Table.objects.create(tenant=other, branch=ob, name="HIDDEN", seats=2)
    Table.objects.create(tenant=tenant, branch=branch, name="MINE", seats=2)

    client = APIClient()
    _auth(client, owner_user, tenant)
    names = {t["name"] for t in client.get("/api/restaurant/tables/").json()["results"]}
    assert names == {"MINE"}


# ---------------------------------------------------------------------------
# REGRESSION: a plain grocery checkout is unaffected by the restaurant code
# ---------------------------------------------------------------------------


def test_plain_checkout_has_no_restaurant_fields(db, tenant, branch, terminal, owner_user, burger):
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(burger.id), "quantity": "3", "unit_price": "450",
                     "tax_rate": "0", "is_taxable": False}],
        payments=[{"payment_method": "cash", "amount": "1350"}],
        client_uuid=uuid.uuid4(),
        # NO order_type / table / modifiers — a normal grocery sale.
    )
    assert inv.order_type is None
    assert inv.table_id is None
    assert inv.order_status is None
    assert inv.grand_total == Decimal("1350.0000")
    item = inv.items.get()
    assert item.modifiers == []
    assert item.course is None
    assert item.sent_to_kitchen is False


# ---------------------------------------------------------------------------
# Modifier attachment + product-scoped filtering
# ---------------------------------------------------------------------------


def test_modifier_groups_filtered_by_product(db, tenant, branch, owner_user, burger):
    from apps.restaurant.models import MenuItemModifierGroup, Modifier, ModifierGroup
    size = ModifierGroup.objects.create(tenant=tenant, name="Size", min_select=1, max_select=1)
    Modifier.objects.create(group=size, name="Large", price_delta=Decimal("100"))
    other = ModifierGroup.objects.create(tenant=tenant, name="Unrelated", min_select=0, max_select=1)
    MenuItemModifierGroup.objects.create(product=burger, group=size)

    client = APIClient()
    _auth(client, owner_user, tenant)

    # No filter → both groups.
    allg = client.get("/api/restaurant/modifier-groups/").json()["results"]
    assert {g["name"] for g in allg} == {"Size", "Unrelated"}

    # ?product= → only the attached group.
    scoped = client.get(f"/api/restaurant/modifier-groups/?product={burger.id}").json()["results"]
    assert {g["name"] for g in scoped} == {"Size"}
    assert other.name not in {g["name"] for g in scoped}


def test_attach_modifier_groups_to_product(db, tenant, branch, owner_user, burger):
    from apps.restaurant.models import ModifierGroup
    g1 = ModifierGroup.objects.create(tenant=tenant, name="Size")
    g2 = ModifierGroup.objects.create(tenant=tenant, name="Add-ons", min_select=0, max_select=3)

    client = APIClient()
    _auth(client, owner_user, tenant)
    url = f"/api/restaurant/products/{burger.id}/modifier-groups/"

    resp = client.put(url, {"group_ids": [str(g1.id), str(g2.id)]}, format="json")
    assert resp.status_code == 200, resp.content
    assert burger.modifier_links.count() == 2

    # GET returns them; PUT with a subset replaces.
    assert set(client.get(url).json()["group_ids"]) == {str(g1.id), str(g2.id)}
    client.put(url, {"group_ids": [str(g1.id)]}, format="json")
    assert burger.modifier_links.count() == 1


# ---------------------------------------------------------------------------
# Open orders — server-synced on send-to-kitchen (live KDS/Floor)
# ---------------------------------------------------------------------------


def test_open_order_created_on_fire_and_shows_on_kds(db, tenant, branch, terminal, owner_user, burger):
    from apps.restaurant.models import Table
    table = Table.objects.create(tenant=tenant, branch=branch, name="T9", seats=4)
    cu = str(uuid.uuid4())

    client = APIClient()
    _auth(client, owner_user, tenant)
    body = {
        "client_uuid": cu,
        "terminal": str(terminal.id),
        "branch": str(branch.id),
        "order_type": "dine_in",
        "table": str(table.id),
        "covers": 3,
        "cart_lines": [
            {"product": str(burger.id), "quantity": "2", "unit_price": "500",
             "tax_rate": "0", "is_taxable": False,
             "modifiers": [{"name": "Extra cheese", "price": "50.0000"}], "item_note": "no mayo"},
        ],
    }
    resp = client.post("/api/restaurant/orders/", body, format="json")
    assert resp.status_code == 200, resp.content
    order_id = resp.json()["id"]

    # It's a held order, sent to kitchen, with the snapshot + restaurant fields.
    inv = Invoice.objects.get(pk=order_id)
    assert inv.is_held and inv.order_status == "sent_to_kitchen"
    assert inv.order_type == "dine_in" and inv.covers == 3
    assert inv.grand_total == Decimal("1000.0000")
    assert inv.items.get().modifiers == [{"name": "Extra cheese", "price": "50.0000"}]

    # Shows live on KDS + floor.
    assert len(client.get("/api/restaurant/kds/").json()["orders"]) == 1
    floor = client.get("/api/restaurant/floor/").json()["tables"]
    t9 = next(t for t in floor if t["name"] == "T9")
    assert t9["order"] is not None

    # Re-fire (idempotent on client_uuid): same order, replaced lines, no dup.
    body["cart_lines"].append({"product": str(burger.id), "quantity": "1", "unit_price": "500",
                               "tax_rate": "0", "is_taxable": False})
    resp2 = client.post("/api/restaurant/orders/", body, format="json")
    assert resp2.json()["id"] == order_id
    assert Invoice.objects.filter(client_uuid=cu).count() == 1
    inv.refresh_from_db()
    assert inv.items.count() == 2

    # Resume payload carries cart_lines to rebuild the cart.
    detail = client.get(f"/api/restaurant/orders/?id={order_id}").json()
    assert len(detail["cart_lines"]) == 2
    assert detail["cart_lines"][0]["product"] == str(burger.id)
