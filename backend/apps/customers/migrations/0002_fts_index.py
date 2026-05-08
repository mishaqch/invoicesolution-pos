"""Postgres gin FTS index over customers (name + phone + cnic)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
    ]
    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS idx_customers_search "
                "ON customers USING gin (to_tsvector('simple', "
                "name || ' ' || coalesce(phone, '') || ' ' || coalesce(cnic, '')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS idx_customers_search;",
        ),
    ]
