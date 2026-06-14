"""Enable the new `warehouses` module for existing Digital-Invoicing tenants.

New DI / both tenants get `warehouses` automatically from
DEFAULT_MODULES_FOR_MODE, but tenants created before this feature need it
appended to their stored `modules_enabled`. POS-only tenants are skipped — they
never get warehouse surfaces. Idempotent; reverse removes it again.
"""

from __future__ import annotations

from django.db import migrations

_DI_MODES = ("digital_invoicing", "both")
_MODULE = "warehouses"


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
    for tenant in Tenant.objects.filter(business_mode__in=_DI_MODES):
        mods = [m for m in (tenant.modules_enabled or []) if m != _MODULE]
        if mods != list(tenant.modules_enabled or []):
            tenant.modules_enabled = mods
            tenant.save(update_fields=["modules_enabled"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0018_alter_tenant_vertical"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
