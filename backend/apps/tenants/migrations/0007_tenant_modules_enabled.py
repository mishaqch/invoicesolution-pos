"""Per-tenant module gates (super-admin-controlled feature catalog).

Adds Tenant.modules_enabled and backfills every existing row with the
full catalog so no live tenant loses access on deploy. Super-admin
trims modules per tenant afterward through the Django admin widget.
"""

from __future__ import annotations

from django.db import migrations, models


def backfill_modules_enabled(apps, schema_editor):
    """Every existing tenant gets the full catalog enabled.

    We import the catalog at runtime (not module-level) so the migration
    can still be replayed if the catalog list changes later — the value
    written here is a snapshot of MODULE_KEYS at the time `migrate` runs.
    """
    from apps.tenants.modules import MODULE_KEYS

    Tenant = apps.get_model("tenants", "Tenant")
    Tenant.objects.filter(modules_enabled=[]).update(
        modules_enabled=list(MODULE_KEYS),
    )


def revert_noop(apps, schema_editor):
    # Reversing the data backfill is meaningless; leaving the column
    # populated is harmless even if you roll back the schema migration.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0006_tenant_account_manager_tenant_internal_notes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="modules_enabled",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Module keys this tenant is allowed to use. Forced "
                    "modules (sales, fbr) are always enabled. Edit via "
                    "the 'Modules enabled' widget on the change form."
                ),
            ),
        ),
        migrations.RunPython(backfill_modules_enabled, revert_noop),
    ]
