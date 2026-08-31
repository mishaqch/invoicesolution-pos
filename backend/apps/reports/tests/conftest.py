"""Shared fixtures for the reports test-suite.

Builds the minimal-but-real object graph a report needs — tenant, branch,
terminal, cashier, a UoM + product, and a small `make_invoice` factory — so
each test can assert on report output against invoices it created itself.

Kept deliberately light: only fields the ORM requires are set; everything
else leans on model defaults.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from django.contrib.auth import get_user_model

from apps.catalog.models import Category, Product, UnitOfMeasure
from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        business_name="Test Retailer",
        ntn=f"NTN{uuid.uuid4().hex[:10]}",
        business_type="sole_proprietor",
        province="PUNJAB",
        # non-fiscal so invoices legitimately stay pending_sync — this is the
        # exact case the reports fix targets.
        fbr_connection_type="none",
    )


@pytest.fixture
def branch(tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MAIN", address="1 Test Road",
    )


@pytest.fixture
def branch2(tenant):
    return Branch.objects.create(
        tenant=tenant, name="Second", code="SEC", address="2 Test Road",
    )


@pytest.fixture
def cashier(tenant):
    User = get_user_model()
    user = User.objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test",
        password="testpass1234",
        full_name="Test Cashier",
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role="cashier")
    return user


@pytest.fixture
def terminal(tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="T1",
        device_fingerprint=uuid.uuid4().hex,
    )


@pytest.fixture
def uom(db):
    obj, _ = UnitOfMeasure.objects.get_or_create(
        code="NOS", defaults={"name_en": "Numbers, pieces, units"},
    )
    return obj


@pytest.fixture
def category(tenant):
    return Category.objects.create(tenant=tenant, name="Food", slug="food")


@pytest.fixture
def product(tenant, uom, category):
    return Product.objects.create(
        tenant=tenant, name="Widget", sku=f"SKU{uuid.uuid4().hex[:6]}",
        uom=uom, category=category, sale_price=Decimal("100.0000"),
    )


@pytest.fixture
def make_invoice(tenant, branch, terminal, cashier, product):
    """Factory: create an invoice (+ one sale item) with sensible defaults.

    Override any field via kwargs — the fix hinges on `status`, `is_held`,
    `deleted_at`, and `invoice_date`, so those are the interesting knobs.
    """
    counter = {"n": 0}

    def _make(
        *,
        invoice_date: dt.date | None = None,
        status: str = "pending_sync",
        is_held: bool = False,
        deleted_at=None,
        grand_total: Decimal = Decimal("100.0000"),
        tax_total: Decimal = Decimal("16.0000"),
        the_branch: Branch | None = None,
        with_item: bool = True,
        quantity: Decimal = Decimal("1"),
        cost_price: Decimal = Decimal("60.0000"),
    ) -> Invoice:
        counter["n"] += 1
        inv = Invoice.objects.create(
            tenant=tenant,
            branch=the_branch or branch,
            terminal=terminal,
            cashier=cashier,
            local_invoice_number=f"INV-{counter['n']:05d}",
            invoice_date=invoice_date or dt.date.today(),
            status=status,
            is_held=is_held,
            deleted_at=deleted_at,
            grand_total=grand_total,
            tax_total=tax_total,
            client_uuid=uuid.uuid4(),
        )
        if with_item:
            SaleItem.objects.create(
                invoice=inv,
                line_number=1,
                product=product,
                product_name=product.name,
                product_sku=product.sku,
                quantity=quantity,
                unit_price=Decimal("100.0000"),
                cost_price=cost_price,
                tax_amount=tax_total,
                line_total=grand_total,
            )
        return inv

    return _make
