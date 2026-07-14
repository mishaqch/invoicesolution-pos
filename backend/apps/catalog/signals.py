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

# applies_to: "goods" | "services" | "both". Services rates matter because
# PRAL rejects the 18% goods rate on a services HS code (chapter 98) with
# errorCode 0046 — services are valid only at 0/Exempt/5/15/16/17%. 16% is the
# common services rate (e.g. commission agents); 15% covers ICT/other cases.
DEFAULT_TAX_RATES = [
    {"name": "Standard 18%", "rate": Decimal("18.00"), "is_default": True, "applies_to": "goods"},
    {"name": "Reduced 8%", "rate": Decimal("8.00"), "is_default": False, "applies_to": "goods"},
    {"name": "Zero rated", "rate": Decimal("0.00"), "is_default": False, "applies_to": "both"},
    {"name": "Exempt", "rate": Decimal("0.00"), "is_default": False, "applies_to": "both"},
    {"name": "Services 16%", "rate": Decimal("16.00"), "is_default": False, "applies_to": "services"},
    {"name": "Services 15%", "rate": Decimal("15.00"), "is_default": False, "applies_to": "services"},
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
                applies_to=row["applies_to"],
                is_default=row["is_default"],
            )
            for row in DEFAULT_TAX_RATES
        ]
    )
