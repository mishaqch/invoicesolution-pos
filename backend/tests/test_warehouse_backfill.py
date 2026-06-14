"""The DI-only warehouse backfill leaves POS tenants alone.

We replay the backfill logic (the same code the data migration runs) against a
DI tenant and a POS tenant in the same DB and assert:
  - the DI tenant's branch gets a default "MAIN" warehouse and its existing
    branch-keyed StockLevel is re-pointed to it;
  - the POS tenant gets no warehouse and its StockLevel keeps warehouse=NULL.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockLevel, Warehouse
from apps.inventory.services.movements import record_movement
from apps.tenants.models import Branch, Tenant


def _make_tenant(business_mode, ntn):
    return Tenant.objects.create(
        business_name=f"T-{business_mode}", ntn=ntn, business_type="sole_proprietor",
        province="PUNJAB", business_mode=business_mode,
    )


def _stocked(tenant, branch):
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="X", sku=f"X-{tenant.id}", uom=uom,
                               sale_price=Decimal("10"), is_taxable=False)
    record_movement(tenant_id=tenant.id, product=p, branch=branch,
                    movement_type="opening_balance", quantity=Decimal("5"))
    return p


# Mirror of apps/inventory/migrations/0004_warehouse_backfill_di.backfill, run
# against live models (migrations are tested via their effect here).
def _run_backfill():
    for tenant in Tenant.objects.filter(business_mode__in=["digital_invoicing", "both"]):
        for branch in Branch.objects.filter(tenant=tenant, deleted_at__isnull=True):
            wh, _ = Warehouse.objects.get_or_create(
                branch=branch, code="MAIN",
                defaults={"tenant_id": tenant.id, "name": "Main",
                          "is_default": True, "is_active": True},
            )
            StockLevel.objects.filter(
                tenant_id=tenant.id, branch=branch, warehouse__isnull=True,
            ).update(warehouse=wh)


@pytest.mark.django_db
def test_backfill_di_creates_default_warehouse_and_repoints_stock():
    di = _make_tenant("digital_invoicing", "1111111")
    di_branch = Branch.objects.create(tenant=di, name="HQ", code="HQ", address="x",
                                      city="K", province="SINDH")
    _stocked(di, di_branch)

    pos = _make_tenant("pos", "2222222")
    pos_branch = Branch.objects.create(tenant=pos, name="Shop", code="SH", address="x",
                                       city="K", province="SINDH")
    _stocked(pos, pos_branch)

    _run_backfill()

    # DI: default MAIN warehouse exists, stock re-pointed onto it.
    wh = Warehouse.objects.get(branch=di_branch, code="MAIN")
    assert wh.is_default is True
    assert StockLevel.objects.filter(tenant_id=di.id, warehouse=wh).count() == 1
    assert not StockLevel.objects.filter(tenant_id=di.id, warehouse__isnull=True).exists()

    # POS: untouched — no warehouse, stock stays branch-keyed (NULL).
    assert not Warehouse.objects.filter(branch=pos_branch).exists()
    assert StockLevel.objects.filter(tenant_id=pos.id, warehouse__isnull=True).count() == 1
