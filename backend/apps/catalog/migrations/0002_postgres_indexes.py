"""Postgres-specific indexes that don't compose with Django's Index() class.

  - gin full-text index on products.name + description (DATABASE_SCHEMA.md §3
    line: idx_products_search USING gin (to_tsvector(...))).
  - gin full-text index on hs_codes.description.
  - partial index on product_batches.expiry_date WHERE current_quantity > 0.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        # Products full-text search
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS idx_products_search "
                "ON products USING gin (to_tsvector('english', "
                "name || ' ' || coalesce(description, '')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS idx_products_search;",
        ),
        # HS code description full-text
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS idx_hs_codes_description "
                "ON hs_codes USING gin (to_tsvector('english', description));"
            ),
            reverse_sql="DROP INDEX IF EXISTS idx_hs_codes_description;",
        ),
        # Partial index on product batches with stock left
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS idx_batches_expiry "
                "ON product_batches(expiry_date) WHERE current_quantity > 0;"
            ),
            reverse_sql="DROP INDEX IF EXISTS idx_batches_expiry;",
        ),
    ]
