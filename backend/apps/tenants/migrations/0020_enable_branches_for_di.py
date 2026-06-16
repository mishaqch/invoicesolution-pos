"""Enable the `branches` module for existing Digital-Invoicing tenants.

New DI / both tenants get `branches` from DEFAULT_MODULES_FOR_MODE, but tenants
created before this change need it appended to their stored modules_enabled so
the Branches page becomes available (multi-location: Branch → Warehouse →
Stock). POS-only tenants already have `branches`; this is idempotent. Reverse
removes it again from DI tenants only.
"""

from __future__ import annotations

from django.db import migrations

_DI_MODES = ("digital_invoicing", "both")
_MODULE = "branches"


def enable(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for tenant in Tenant.objects.filter(business_mode__in=_DI_MODES):
        mods = list(tenant.modules_enabled or [])
        if _MODULE not in mods:
            mods.append(_MODULE)
            tenant.modules_enabled = mods
            tenant.save(update_fields=["modules_enabled"])


def disable(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    # Only strip it from DI tenants (POS/both legitimately keep branches).
    for tenant in Tenant.objects.filter(business_mode="digital_invoicing"):
        mods = [m for m in (tenant.modules_enabled or []) if m != _MODULE]
        if mods != list(tenant.modules_enabled or []):
            tenant.modules_enabled = mods
            tenant.save(update_fields=["modules_enabled"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0019_enable_warehouses_for_di"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
