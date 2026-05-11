"""Implicit branch + terminal flow for office-invoice tenants.

Closes the "branchless seller" use case: a tenant whose business
shape is wholesale / service / consulting / freelance — no physical
store, no cash counters — should be able to create FBR-validated
invoices from a laptop without ever encountering a "branch" or
"terminal" concept.

The server provisions a single hidden default Branch + Terminal the
first time the tenant calls /api/sales/invoices/manual/. Subsequent
invoices reuse the same pair. The tenant's React admin never shows
either picker (their `branches`/`terminals` modules are disabled).
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
from apps.tenants.implicit import ensure_implicit_branch_and_terminal
from apps.tenants.models import Branch, Terminal


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post(
        "/api/auth/login/",
        {"email": email, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


@pytest.fixture
def stocked_product(db, tenant):
    """A product without explicit stock — manual invoices for service /
    digital goods skip the stock-movement path. The factory still
    creates a Branch + Terminal in the implicit path on its own."""
    return Product.objects.create(
        tenant=tenant, name="Consulting hour", sku="CONS-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("2500"), cost_price=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# ensure_implicit_branch_and_terminal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_implicit_creates_default_branch_and_terminal(tenant):
    """Brand-new tenant with no branches/terminals: helper creates one
    of each, both marked active. Codes match the documented sentinels."""
    assert Branch.objects.filter(tenant=tenant).count() == 0
    assert Terminal.objects.filter(tenant=tenant).count() == 0

    branch, terminal = ensure_implicit_branch_and_terminal(tenant)

    assert branch.tenant == tenant
    assert branch.code == "HQ"
    assert branch.is_default is True
    assert branch.is_active is True

    assert terminal.tenant == tenant
    assert terminal.branch == branch
    assert terminal.name == "Office"
    assert terminal.is_active is True

    # And we created exactly one of each — no duplicates.
    assert Branch.objects.filter(tenant=tenant).count() == 1
    assert Terminal.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_implicit_is_idempotent(tenant):
    """Calling the helper twice should NOT create two branches —
    the second call reuses what's already there."""
    b1, t1 = ensure_implicit_branch_and_terminal(tenant)
    b2, t2 = ensure_implicit_branch_and_terminal(tenant)

    assert b1 == b2
    assert t1 == t2
    assert Branch.objects.filter(tenant=tenant).count() == 1
    assert Terminal.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_implicit_reuses_existing_branch_if_one_already_exists(tenant):
    """A tenant who once had branches enabled (now disabled by super-
    admin) should NOT get a second implicit branch — we reuse the
    first existing branch instead."""
    existing = Branch.objects.create(
        tenant=tenant, name="Lahore", code="LHR",
        address="x", city="Lahore", province="PUNJAB", is_active=True,
    )
    branch, terminal = ensure_implicit_branch_and_terminal(tenant)
    assert branch == existing
    # Terminal under that branch is freshly created.
    assert terminal.branch == existing
    assert Branch.objects.filter(tenant=tenant).count() == 1


# ---------------------------------------------------------------------------
# /api/sales/invoices/manual/ — office-invoice flow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_manual_invoice_without_branch_terminal_uses_implicit(
    tenant, owner_user, stocked_product,
):
    """Shape B tenant: posts to /manual/ with no branch/terminal in
    the body. Server creates implicit defaults and the invoice is
    bound to them. The next request reuses the same pair."""
    api = APIClient()
    _login(api, owner_user.email)

    body = {
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "2",
            "unit_price": "2500",
            "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "5900"}],
        "client_uuid": str(uuid.uuid4()),
    }

    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay") as mock_submit:
        r1 = api.post("/api/sales/invoices/manual/", body, format="json")
    assert r1.status_code == 201, r1.content
    inv1 = Invoice.objects.get(pk=r1.json()["id"])
    assert inv1.branch.code == "HQ"
    assert inv1.terminal.name == "Office"
    mock_submit.assert_called_once_with(str(inv1.id))

    # Second invoice (different client_uuid) reuses the same pair.
    body["client_uuid"] = str(uuid.uuid4())
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        r2 = api.post("/api/sales/invoices/manual/", body, format="json")
    inv2 = Invoice.objects.get(pk=r2.json()["id"])
    assert inv2.branch_id == inv1.branch_id
    assert inv2.terminal_id == inv1.terminal_id


@pytest.mark.django_db
def test_manual_invoice_with_explicit_branch_terminal_still_works(
    tenant, owner_user, stocked_product,
):
    """Shape A tenant with branches/terminals modules ON: the existing
    flow that posts explicit UUIDs continues to work unchanged.
    Implicit fallback only fires when the UUIDs are absent."""
    branch = Branch.objects.create(
        tenant=tenant, name="HQ", code="HQ",
        address="x", city="x", province="SINDH",
    )
    terminal = Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1",
        device_fingerprint="explicit-fp",
    )

    # Stock the product so the explicit-branch flow with stock movements works.
    record_movement(
        tenant_id=tenant.id, product=stocked_product, branch=branch,
        movement_type="opening_balance", quantity=Decimal("10"),
    )

    api = APIClient()
    _login(api, owner_user.email)
    body = {
        "branch": str(branch.id),
        "terminal": str(terminal.id),
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "2500", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "2950"}],
        "client_uuid": str(uuid.uuid4()),
    }
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay"):
        resp = api.post("/api/sales/invoices/manual/", body, format="json")
    assert resp.status_code == 201, resp.content
    inv = Invoice.objects.get(pk=resp.json()["id"])
    assert inv.branch_id == branch.id
    assert inv.terminal_id == terminal.id


@pytest.mark.django_db
def test_pos_checkout_still_requires_explicit_branch_terminal(
    tenant, owner_user, stocked_product,
):
    """POS /checkout/ is for cashiers at a physical counter — the
    implicit-default fallback does NOT apply there. Missing
    branch/terminal must be rejected with 400."""
    api = APIClient()
    _login(api, owner_user.email)
    body = {
        # NO branch, NO terminal
        "cart_lines": [{
            "product": str(stocked_product.id),
            "quantity": "1", "unit_price": "100", "tax_rate": "18",
            "is_taxable": True,
        }],
        "payments": [{"payment_method": "cash", "amount": "118"}],
        "client_uuid": str(uuid.uuid4()),
    }
    resp = api.post("/api/sales/invoices/checkout/", body, format="json")
    assert resp.status_code == 400
    assert "branch and terminal" in str(resp.json()).lower()
