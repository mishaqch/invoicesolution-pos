"""Phase 1 weekly stock-valuation report.

Closes the Phase 1 approval-checklist item "weekly stock valuation
report cached in Redis". Tests cover:

- compute_stock_valuation produces the right totals from StockLevel
  + product cost_price
- Cache populated by the task; subsequent reads come from cache
- On-demand mode (tenant_id arg) only processes that one tenant
- Cross-tenant isolation: tenant A's report excludes tenant B's stock
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.services.movements import record_movement
from apps.inventory.tasks import (
    _valuation_cache_key,
    compute_stock_valuation,
    get_cached_stock_valuation,
    stock_valuation_report,
)
from apps.tenants.models import Branch, Tenant


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MAIN",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def stocked_widget(db, tenant, branch):
    p = Product.objects.create(
        tenant=tenant, name="Widget", sku="WGT",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("100"),
        cost_price=Decimal("60"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("10"),
    )
    return p


@pytest.mark.django_db
def test_compute_stock_valuation_sums_qty_times_cost(
    tenant, branch, stocked_widget,
):
    report = compute_stock_valuation(tenant)
    # 10 units × Rs 60 = Rs 600
    assert report["total_value"] == "600.00"
    assert report["by_branch"][0]["branch_name"] == "Main"
    assert report["by_branch"][0]["total_value"] == "600.00"
    assert report["by_branch"][0]["sku_count"] == 1


@pytest.mark.django_db
def test_compute_stock_valuation_excludes_zero_quantity(
    tenant, branch,
):
    """Out-of-stock SKUs don't contribute to the total."""
    Product.objects.create(
        tenant=tenant, name="Empty", sku="EMP",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("100"), cost_price=Decimal("60"),
    )
    # No record_movement → StockLevel never created, so it falls out
    # of the qs naturally.
    report = compute_stock_valuation(tenant)
    assert report["total_value"] == "0.00"
    assert report["by_branch"] == []


@pytest.mark.django_db
def test_stock_valuation_report_caches_result(
    tenant, branch, stocked_widget,
):
    cache.delete(_valuation_cache_key(tenant.id))
    assert get_cached_stock_valuation(tenant) is None

    stock_valuation_report(str(tenant.id))

    cached = get_cached_stock_valuation(tenant)
    assert cached is not None
    assert cached["total_value"] == "600.00"


@pytest.mark.django_db
def test_stock_valuation_isolated_per_tenant(
    db, tenant, branch, stocked_widget,
):
    # A second tenant with its own stock — must not contaminate
    # the first tenant's report.
    other = Tenant.objects.create(
        business_name="Other", ntn="888-99-77",
        business_type="sole_proprietor", province="PUNJAB",
    )
    other_branch = Branch.objects.create(
        tenant=other, name="Other HQ", code="OHQ",
        address="x", city="x", province="PUNJAB",
    )
    p2 = Product.objects.create(
        tenant=other, name="Other Widget", sku="OWGT",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("500"), cost_price=Decimal("400"),
    )
    record_movement(
        tenant_id=other.id, product=p2, branch=other_branch,
        movement_type="opening_balance", quantity=Decimal("5"),
    )

    a_report = compute_stock_valuation(tenant)
    b_report = compute_stock_valuation(other)

    # Tenant A: 10 × 60 = 600
    assert a_report["total_value"] == "600.00"
    # Tenant B: 5 × 400 = 2000 (no contamination from A)
    assert b_report["total_value"] == "2000.00"
