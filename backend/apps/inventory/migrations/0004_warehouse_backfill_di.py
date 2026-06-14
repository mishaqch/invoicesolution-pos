"""Backfill default warehouses for Digital-Invoicing tenants only.

For every DI tenant (business_mode in {digital_invoicing, both}) we:
  1. create a default "MAIN" warehouse inside each of its live branches, and
  2. re-point that tenant's existing branch-keyed StockLevel rows (warehouse
     NULL) to the branch's default warehouse, so the DI stock view shows the
     on-hand they already had.

POS tenants are left completely untouched: no warehouse is created for them
and their StockLevel rows keep warehouse=NULL, so the legacy
(product, variant, branch) partial unique constraint and the Stock-by-branch
pages behave exactly as before.

We deliberately do NOT touch stock_movements: it is append-only (DB REVOKEs
UPDATE/DELETE + signal guards), and historical movements keeping warehouse=NULL
is fine — StockLevel is the source of on-hand truth. Forward-only; the reverse
is a safe no-op (leaving warehouses + re-pointed levels in place does no harm).
"""

from __future__ import annotations

from django.db import migrations

_DI_MODES = ("digital_invoicing", "both")
_DEFAULT_WAREHOUSE_CODE = "MAIN"
_DEFAULT_WAREHOUSE_NAME = "Main"


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Branch = apps.get_model("tenants", "Branch")
    Warehouse = apps.get_model("inventory", "Warehouse")
    StockLevel = apps.get_model("inventory", "StockLevel")

    di_tenant_ids = list(
        Tenant.objects.filter(business_mode__in=_DI_MODES).values_list("id", flat=True)
    )
    for tenant_id in di_tenant_ids:
        branches = Branch.objects.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        for branch in branches:
            wh, _ = Warehouse.objects.get_or_create(
                branch=branch,
                code=_DEFAULT_WAREHOUSE_CODE,
                defaults={
                    "tenant_id": tenant_id,
                    "name": _DEFAULT_WAREHOUSE_NAME,
                    "is_default": True,
                    "is_active": True,
                },
            )
            # Re-point this branch's legacy (warehouse-NULL) stock levels onto
            # the new default warehouse. StockLevel is freely mutable.
            StockLevel.objects.filter(
                tenant_id=tenant_id,
                branch=branch,
                warehouse__isnull=True,
            ).update(warehouse=wh)


def noop_reverse(apps, schema_editor):
    # Forward-only data migration. Leaving the backfilled warehouses and the
    # re-pointed stock levels in place on reverse is harmless.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_warehouse_and_more"),
        ("tenants", "0018_alter_tenant_vertical"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
