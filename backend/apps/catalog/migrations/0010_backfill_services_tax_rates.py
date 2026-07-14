"""Backfill services tax rates (16% / 15%) for EXISTING tenants.

The seed signal only fires on tenant creation, so tenants created before the
"Services 16%/15%" rates were added have no valid services rate — and PRAL
rejects the 18% goods rate on a services HS code (chapter 98) with errorCode
0046. This migration adds the two services rates to every tenant that doesn't
already have a rate by that name (idempotent).
"""

from decimal import Decimal

from django.db import migrations

SERVICES_RATES = [
    ("Services 16%", Decimal("16.00")),
    ("Services 15%", Decimal("15.00")),
]


def forward(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    TaxRate = apps.get_model("catalog", "TaxRate")
    to_create = []
    for tenant in Tenant.objects.all():
        existing = set(
            TaxRate.objects.filter(tenant=tenant).values_list("name", flat=True)
        )
        for name, rate in SERVICES_RATES:
            if name in existing:
                continue
            to_create.append(
                TaxRate(
                    tenant=tenant,
                    name=name,
                    rate=rate,
                    applies_to="services",
                    is_default=False,
                )
            )
    if to_create:
        TaxRate.objects.bulk_create(to_create)


def backward(apps, schema_editor):
    TaxRate = apps.get_model("catalog", "TaxRate")
    TaxRate.objects.filter(name__in=[n for n, _ in SERVICES_RATES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_seed_services_uom"),
    ]
    operations = [migrations.RunPython(forward, backward)]
