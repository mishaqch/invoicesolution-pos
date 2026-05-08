"""Catalog signals.

On Tenant creation, seed the standard set of tax rates so a fresh tenant has
'Standard 18%' / 'Reduced 8%' / 'Zero rated' / 'Exempt' available immediately.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tenants.models import Tenant

from .models import TaxRate

DEFAULT_TAX_RATES = [
    {"name": "Standard 18%", "rate": Decimal("18.00"), "is_default": True},
    {"name": "Reduced 8%", "rate": Decimal("8.00"), "is_default": False},
    {"name": "Zero rated", "rate": Decimal("0.00"), "is_default": False},
    {"name": "Exempt", "rate": Decimal("0.00"), "is_default": False},
]


@receiver(post_save, sender=Tenant)
def seed_default_tax_rates(sender, instance: Tenant, created: bool, **kwargs):
    if not created:
        return
    if TaxRate.objects.filter(tenant=instance).exists():
        return
    TaxRate.objects.bulk_create(
        [
            TaxRate(
                tenant=instance,
                name=row["name"],
                rate=row["rate"],
                applies_to="goods",
                is_default=row["is_default"],
            )
            for row in DEFAULT_TAX_RATES
        ]
    )
