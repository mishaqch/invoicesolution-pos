"""FBR edit/cancel rules — every cell of the constraint matrix."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.rules import can_cancel_invoice, can_cancel_item, can_edit_item
from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Terminal


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="X", code="X",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="rules-fp-1",
    )


@pytest.fixture
def product(db, tenant):
    return Product.objects.create(
        tenant=tenant, name="P", sku="P",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("100"),
    )


def _make(*, tenant, branch, terminal, cashier, product, **invoice_overrides):
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=cashier,
        local_invoice_number=f"X-T1-2026-{invoice_overrides.pop('seq', '0000001')}",
        invoice_date=dt.date.today(),
        subtotal=Decimal("100"), tax_total=Decimal("18"),
        grand_total=Decimal("118"), paid_total=Decimal("118"),
        client_uuid=invoice_overrides.pop("uuid",
                                          "22222222-1111-1111-1111-111111111111"),
        edit_deadline_at=invoice_overrides.pop("deadline",
                                                timezone.now() + dt.timedelta(hours=24)),
        status=invoice_overrides.pop("status", "valid"),
        **invoice_overrides,
    )
    item = SaleItem.objects.create(
        invoice=inv, line_number=1, product=product,
        product_name=product.name, product_sku=product.sku,
        uom_code="PCS", quantity=Decimal("1"), unit_price=Decimal("100"),
        tax_rate=Decimal("18"), tax_amount=Decimal("18"),
        line_total=Decimal("118"),
    )
    return inv, item


# ---------------------------------------------------------------------------
# can_edit_item
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_can_edit_within_window(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    ok, why = can_edit_item(inv, item)
    assert ok and why is None


@pytest.mark.django_db
def test_cannot_edit_after_deadline(tenant, branch, terminal, owner_user, product):
    inv, item = _make(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
        deadline=timezone.now() - dt.timedelta(hours=1),
    )
    ok, why = can_edit_item(inv, item)
    assert not ok and "72-hour" in why


@pytest.mark.django_db
def test_cannot_edit_already_edited_item(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    item.edit_count = 1
    item.is_edited = True
    item.save()
    ok, why = can_edit_item(inv, item)
    assert not ok and "already been edited" in why


@pytest.mark.django_db
def test_cannot_edit_cancelled_item(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    item.is_cancelled = True
    item.save()
    ok, why = can_edit_item(inv, item)
    assert not ok and "cancelled" in why


@pytest.mark.django_db
def test_cannot_edit_finalized_invoice(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product, status="finalized")
    ok, why = can_edit_item(inv, item)
    assert not ok and "submitted return" in why


@pytest.mark.django_db
def test_cannot_edit_annexure_c_linked(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    inv.is_annexure_c_linked = True
    inv.save()
    ok, why = can_edit_item(inv, item)
    assert not ok and "Annexure-C" in why


# ---------------------------------------------------------------------------
# can_cancel_item
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_can_cancel_item_within_window(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    ok, _ = can_cancel_item(inv, item)
    assert ok


@pytest.mark.django_db
def test_cannot_cancel_already_cancelled_item(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    item.is_cancelled = True
    item.save()
    ok, why = can_cancel_item(inv, item)
    assert not ok and "cancelled" in why


@pytest.mark.django_db
def test_cannot_cancel_edited_item(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    item.is_edited = True
    item.save()
    ok, why = can_cancel_item(inv, item)
    assert not ok and "edited" in why


# ---------------------------------------------------------------------------
# can_cancel_invoice
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_can_cancel_invoice_clean(tenant, branch, terminal, owner_user, product):
    inv, _ = _make(tenant=tenant, branch=branch, terminal=terminal,
                    cashier=owner_user, product=product)
    ok, _ = can_cancel_invoice(inv)
    assert ok


@pytest.mark.django_db
def test_cannot_cancel_if_any_item_edited(tenant, branch, terminal, owner_user, product):
    inv, item = _make(tenant=tenant, branch=branch, terminal=terminal,
                       cashier=owner_user, product=product)
    item.is_edited = True
    item.save()
    ok, why = can_cancel_invoice(inv)
    assert not ok and "edited" in why


@pytest.mark.django_db
def test_cannot_cancel_after_deadline(tenant, branch, terminal, owner_user, product):
    inv, _ = _make(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
        deadline=timezone.now() - dt.timedelta(hours=1),
    )
    ok, why = can_cancel_invoice(inv)
    assert not ok and "72-hour" in why


@pytest.mark.django_db
def test_cannot_cancel_finalized(tenant, branch, terminal, owner_user, product):
    inv, _ = _make(tenant=tenant, branch=branch, terminal=terminal,
                    cashier=owner_user, product=product, status="finalized")
    ok, why = can_cancel_invoice(inv)
    assert not ok and "finalized" in why
