"""Make audit_log append-only at the database level.

Same pattern as inventory.0002_immutable_movements. The Django pre_save /
pre_delete signal in apps/audit/signals.py is the early-warning; this
migration is the source of truth.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]
    operations = [
        migrations.RunSQL(
            sql=(
                "REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC; "
                "DO $$ BEGIN "
                "  EXECUTE format('REVOKE UPDATE, DELETE ON audit_log FROM %I', current_user); "
                "EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;"
            ),
            reverse_sql=(
                "GRANT UPDATE, DELETE ON audit_log TO PUBLIC; "
                "DO $$ BEGIN "
                "  EXECUTE format('GRANT UPDATE, DELETE ON audit_log TO %I', current_user); "
                "EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;"
            ),
        ),
    ]
