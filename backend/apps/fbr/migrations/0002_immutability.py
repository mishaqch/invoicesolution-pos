"""Append-only fbr_submissions + immutable fbr_invoice_number trigger.

Same defense-in-depth pattern as audit_log / stock_movements. The signal
in apps/fbr/signals.py is the early-warning; this migration is the truth.

Trigger: once invoices.fbr_invoice_number is non-NULL, it can never
change. New value still allowed (transition NULL → non-NULL on validation),
but UPDATE that swaps a non-NULL value for a different value is rejected.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("fbr", "0001_initial"),
        ("sales", "0002_invoice_is_annexure_c_linked"),
    ]

    operations = [
        # 1. fbr_submissions append-only
        migrations.RunSQL(
            sql=(
                "REVOKE UPDATE, DELETE ON fbr_submissions FROM PUBLIC; "
                "DO $$ BEGIN "
                "  EXECUTE format('REVOKE UPDATE, DELETE ON fbr_submissions FROM %I', current_user); "
                "EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;"
            ),
            reverse_sql=(
                "GRANT UPDATE, DELETE ON fbr_submissions TO PUBLIC; "
                "DO $$ BEGIN "
                "  EXECUTE format('GRANT UPDATE, DELETE ON fbr_submissions TO %I', current_user); "
                "EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;"
            ),
        ),

        # 2. invoices.fbr_invoice_number immutable once set
        migrations.RunSQL(
            sql=(
                "CREATE OR REPLACE FUNCTION block_fbr_invoice_number_update() "
                "RETURNS trigger AS $$ "
                "BEGIN "
                "  IF OLD.fbr_invoice_number IS NOT NULL "
                "     AND OLD.fbr_invoice_number IS DISTINCT FROM NEW.fbr_invoice_number THEN "
                "    RAISE EXCEPTION 'fbr_invoice_number is immutable once set'; "
                "  END IF; "
                "  RETURN NEW; "
                "END; "
                "$$ LANGUAGE plpgsql; "
                "DROP TRIGGER IF EXISTS trg_immutable_fbr_invoice_number ON invoices; "
                "CREATE TRIGGER trg_immutable_fbr_invoice_number "
                "BEFORE UPDATE ON invoices "
                "FOR EACH ROW EXECUTE FUNCTION block_fbr_invoice_number_update();"
            ),
            reverse_sql=(
                "DROP TRIGGER IF EXISTS trg_immutable_fbr_invoice_number ON invoices; "
                "DROP FUNCTION IF EXISTS block_fbr_invoice_number_update();"
            ),
        ),
    ]
