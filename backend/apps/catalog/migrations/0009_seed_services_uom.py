"""Seed the "Others" unit of measure (plus SET / NO) needed for services.

Services HS codes (chapter 98) require PRAL's "Others" uoM — the retail seed
(0003) never included it, so it was missing from the product/invoice UoM
dropdown. Add it (and the two other generic PRAL units, SET and NO) so an
operator can pick them. The FBR string each maps to lives in fbr.builder
(OTHER -> "Others", SET -> "SET", NO -> "NO").
"""

from django.db import migrations

UOM_SEEDS = [
    # code, name_en, name_ur, is_decimal_quantity
    ("OTHER", "Others (services)", "دیگر", False),
    ("SET",   "Set",               "سیٹ",  False),
    ("NO",    "Number",            "نمبر", False),
]


def forward(apps, schema_editor):
    UnitOfMeasure = apps.get_model("catalog", "UnitOfMeasure")
    for code, name_en, name_ur, is_decimal in UOM_SEEDS:
        UnitOfMeasure.objects.update_or_create(
            code=code,
            defaults={
                "name_en": name_en,
                "name_ur": name_ur,
                "is_decimal_quantity": is_decimal,
            },
        )


def backward(apps, schema_editor):
    UnitOfMeasure = apps.get_model("catalog", "UnitOfMeasure")
    UnitOfMeasure.objects.filter(code__in=[row[0] for row in UOM_SEEDS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_remove_product_uniq_product_tenant_sku_and_more"),
    ]
    operations = [migrations.RunPython(forward, backward)]
