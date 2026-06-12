"""Reconcile an invoice cancelled directly on the FBR portal.

PRAL has no status-query endpoint, so a portal-side cancellation can't be
detected automatically. The mark-cancelled-on-fbr action lets an owner/manager
record it: flips local status to 'cancelled', no PRAL call, no budget use.

Also covers the invoices-list status filter accepting a comma list
("valid,finalized") so the "Validated" tile rows match its count.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import Product, UnitOfMeasure
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
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-mcof-1",
    )


@pytest.fixture
def product(db, tenant):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="Widget", sku="W-1", uom=uom,
        sale_price=Decimal("100"), is_taxable=False,
    )


def _validated_invoice(tenant, branch, terminal, owner_user, product, *, status="finalized"):
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(product.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "0", "is_taxable": False}],
        payments=[{"payment_method": "cash", "amount": "100"}],
        client_uuid=str(uuid.uuid4()),
    )
    inv.fbr_invoice_number = uuid.uuid4().hex[:24].upper()  # unique per invoice
    inv.status = status
    inv.save(update_fields=["fbr_invoice_number", "status"])
    return inv


def test_mark_cancelled_on_fbr_sets_cancelled(db, tenant, branch, terminal, owner_user, product):
    inv = _validated_invoice(tenant, branch, terminal, owner_user, product, status="finalized")
    client = APIClient()
    _auth(client, owner_user, tenant)

    resp = client.post(f"/api/sales/invoices/{inv.id}/mark-cancelled-on-fbr/")
    assert resp.status_code == 200, resp.content
    inv.refresh_from_db()
    assert inv.status == "cancelled"

    # Audit row recorded.
    from apps.audit.models import AuditLog
    assert AuditLog.objects.filter(entity_id=inv.id, action="cancelled_on_fbr_portal").exists()

    # Idempotent.
    resp2 = client.post(f"/api/sales/invoices/{inv.id}/mark-cancelled-on-fbr/")
    assert resp2.status_code == 200


def test_mark_cancelled_on_fbr_rejects_invoice_without_fbr_number(db, tenant, branch, terminal, owner_user, product):
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(product.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "0", "is_taxable": False}],
        payments=[{"payment_method": "cash", "amount": "100"}],
        client_uuid=str(uuid.uuid4()),
    )  # no fbr_invoice_number
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.post(f"/api/sales/invoices/{inv.id}/mark-cancelled-on-fbr/")
    assert resp.status_code == 400


def test_cashier_cannot_mark_cancelled_on_fbr(db, tenant, branch, terminal, owner_user, product):
    from django.contrib.auth import get_user_model
    from apps.tenants.models import TenantMembership
    User = get_user_model()
    cashier = User.objects.create_user(
        email="floor-cashier@example.com", password="testpass1234", full_name="Floor Cashier",
    )
    TenantMembership.objects.create(tenant=tenant, user=cashier, role="cashier")

    inv = _validated_invoice(tenant, branch, terminal, owner_user, product)
    client = APIClient()
    _auth(client, cashier, tenant)
    resp = client.post(f"/api/sales/invoices/{inv.id}/mark-cancelled-on-fbr/")
    assert resp.status_code == 403


def test_status_filter_accepts_comma_list(db, tenant, branch, terminal, owner_user, product):
    _validated_invoice(tenant, branch, terminal, owner_user, product, status="valid")
    _validated_invoice(tenant, branch, terminal, owner_user, product, status="finalized")
    client = APIClient()
    _auth(client, owner_user, tenant)

    # "valid,finalized" returns both; "valid" alone returns one.
    both = client.get("/api/sales/invoices/?status=valid,finalized").json()
    assert both["count"] == 2
    just_valid = client.get("/api/sales/invoices/?status=valid").json()
    assert just_valid["count"] == 1
