"""Seed standard Pakistani retail units of measure.

Ships 20 entries covering the most common cases. Tenants can add their own
later via the admin or a migration of their own.

Decimal-quantity flag controls whether the POS allows fractional input
(KG yes, PCS no).
"""

from django.db import migrations

UOM_SEEDS = [
    # code, name_en, name_ur, is_decimal_quantity
    ("PCS",     "Numbers, pieces, units", "عدد",      False),
    ("DOZEN",   "Dozen",                  "درجن",     False),
    ("PACK",    "Pack",                   "پیکٹ",     False),
    ("BOX",     "Box",                    "ڈبہ",       False),
    ("CARTON",  "Carton",                 "کارٹن",    False),
    ("BAG",     "Bag",                    "بوری",      False),
    ("BOTTLE",  "Bottle",                 "بوتل",      False),
    ("TIN",     "Tin",                    "ٹن",        False),
    ("PAIR",    "Pair",                   "جوڑا",      False),
    ("ROLL",    "Roll",                   "رول",       False),
    ("SHEET",   "Sheet",                  "شیٹ",       False),
    ("KG",      "Kilograms",              "کلوگرام",  True),
    ("GM",      "Grams",                  "گرام",      True),
    ("MG",      "Milligrams",             "ملی گرام", True),
    ("LTR",     "Liters",                 "لیٹر",      True),
    ("ML",      "Milliliters",            "ملی لیٹر", True),
    ("METER",   "Meters",                 "میٹر",      True),
    ("CM",      "Centimeters",            "سینٹی میٹر",True),
    ("MM",      "Millimeters",            "ملی میٹر", True),
    ("SQM",     "Square Meters",          "مربع میٹر",True),
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
        ("catalog", "0002_postgres_indexes"),
    ]
    operations = [migrations.RunPython(forward, backward)]
