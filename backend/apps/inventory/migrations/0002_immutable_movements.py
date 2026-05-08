"""Make stock_movements append-only at the database level + low-stock partial index.

The REVOKE here is the source of truth for immutability. The Django pre_save
signal in apps/inventory/signals.py is an early-warning that catches ORM
misuse — but a shell open against the prod DB still cannot UPDATE or DELETE
this table because of these grants.

Note: REVOKE is per-role. We revoke from PUBLIC and from the active app role
(read from current_user when the migration runs). DBAs / superusers retain
full access for legitimate maintenance.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "REVOKE UPDATE, DELETE ON stock_movements FROM PUBLIC; "
                "DO $$ BEGIN "
                "  EXECUTE format('REVOKE UPDATE, DELETE ON stock_movements FROM %I', current_user); "
                "EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;"
            ),
            reverse_sql=(
                "GRANT UPDATE, DELETE ON stock_movements TO PUBLIC; "
                "DO $$ BEGIN "
                "  EXECUTE format('GRANT UPDATE, DELETE ON stock_movements TO %I', current_user); "
                "EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;"
            ),
        ),
        # Partial index: low-stock query filter
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS idx_stock_low "
                "ON stock_levels(tenant_id) "
                "WHERE quantity <= COALESCE(reorder_level, 0);"
            ),
            reverse_sql="DROP INDEX IF EXISTS idx_stock_low;",
        ),
    ]
