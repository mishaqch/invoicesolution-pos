"""pick_scenario_id — the shared sandbox scenarioId chooser for submit + validate.

Regression for the M/S New Mubashar Autos bug: the validate path hard-coded
SN007 ("Zero-Rated 5th Schedule") for 3rd-Schedule invoices, so PRAL rejected
with errorCode 0204 ("Sale type not match with provided scenario SN007"). The
picker must use SN008/SN027 for 3rd-Schedule, never SN007, and only emit
scenarios the tenant is actually assigned.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.scenarios import pick_scenario_id
from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Terminal


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MN", address="x", city="K", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-sc-1",
    )


def _product(tenant):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="X", sku=f"X-{uuid.uuid4().hex[:6]}", uom=uom,
        sale_price=Decimal("100"), is_taxable=True,
    )


def _invoice(tenant, branch, terminal, owner_user, *, registered=False):
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        local_invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        client_uuid=uuid.uuid4(), invoice_date="2026-06-15",
        subtotal=0, tax_total=0, grand_total=0, paid_total=0,
        buyer_registration_type="Registered" if registered else "Unregistered",
    )


def _add_item(invoice, product, *, fixed_notified=None, sale_type="Goods at standard rate (default)"):
    return SaleItem.objects.create(
        invoice=invoice, line_number=1, product=product,
        product_name=product.name, product_sku=product.sku, uom_code="PCS",
        quantity=Decimal("1"), unit_price=Decimal("100"),
        tax_rate=Decimal("18"), tax_amount=Decimal("18"), line_total=Decimal("118"),
        fixed_notified_value=fixed_notified, sale_type=sale_type,
    )


def _assign(tenant, codes):
    tenant.assigned_scenarios = list(codes)
    tenant.save(update_fields=["assigned_scenarios"])


def test_production_returns_none(db, tenant, branch, terminal, owner_user):
    inv = _invoice(tenant, branch, terminal, owner_user)
    _add_item(inv, _product(tenant))
    assert pick_scenario_id(inv, "production") is None


def test_third_schedule_never_sn007(db, tenant, branch, terminal, owner_user):
    """The actual bug: all-3rd-Schedule must pick SN008 (or retail SN027) —
    NEVER SN007 (which is Zero-Rated, a different scenario)."""
    _assign(tenant, ["SN001", "SN002", "SN008", "SN026", "SN027", "SN028"])
    inv = _invoice(tenant, branch, terminal, owner_user)  # walk-in
    _add_item(inv, _product(tenant), fixed_notified=Decimal("250"), sale_type="3rd Schedule Goods")
    picked = pick_scenario_id(inv, "sandbox")
    assert picked != "SN007"
    # Walk-in + SN027 assigned → retail SN027.
    assert picked == "SN027"


def test_third_schedule_without_retail_scenario_falls_back_to_sn008(db, tenant, branch, terminal, owner_user):
    _assign(tenant, ["SN001", "SN002", "SN008"])  # no SN027
    inv = _invoice(tenant, branch, terminal, owner_user)
    _add_item(inv, _product(tenant), fixed_notified=Decimal("250"), sale_type="3rd Schedule Goods")
    assert pick_scenario_id(inv, "sandbox") == "SN008"


def test_standard_walk_in_sn002(db, tenant, branch, terminal, owner_user):
    _assign(tenant, ["SN001", "SN002"])
    inv = _invoice(tenant, branch, terminal, owner_user)  # walk-in
    _add_item(inv, _product(tenant))
    assert pick_scenario_id(inv, "sandbox") == "SN002"


def test_standard_registered_sn001(db, tenant, branch, terminal, owner_user):
    _assign(tenant, ["SN001", "SN002"])
    inv = _invoice(tenant, branch, terminal, owner_user, registered=True)
    _add_item(inv, _product(tenant))
    assert pick_scenario_id(inv, "sandbox") == "SN001"


def test_standard_walk_in_prefers_retail_sn026_when_assigned(db, tenant, branch, terminal, owner_user):
    _assign(tenant, ["SN001", "SN002", "SN026"])
    inv = _invoice(tenant, branch, terminal, owner_user)  # walk-in
    _add_item(inv, _product(tenant))
    assert pick_scenario_id(inv, "sandbox") == "SN026"
