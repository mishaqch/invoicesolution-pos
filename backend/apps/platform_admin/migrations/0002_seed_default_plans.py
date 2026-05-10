"""Seed the 3 default subscription plans + create PlatformSettings singleton.

Prices in paisa (1 PKR = 100 paisa). These are starting points; the platform
team is expected to edit via Django admin during V1 to find what works.
The plan codes are stable (Phase 9 references them); names + prices are
not.
"""

from django.db import migrations


DEFAULT_PLANS = [
    {
        "code": "starter",
        "name": "Starter",
        "description": "For single-shop owners getting started with FBR-compliant invoicing.",
        "monthly_price_paisa": 200_000,    # Rs 2,000
        "yearly_price_paisa": 2_000_000,   # Rs 20,000 (2 months free)
        "max_branches": 1,
        "max_terminals": 2,
        "max_products": 1000,
        "max_users": 3,
        "features": {
            "fbr_integration": True,
            "csv_import": True,
            "reports": "basic",
            "support": "email",
        },
        "sort_order": 1,
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "For growing businesses with multiple branches and full reporting.",
        "monthly_price_paisa": 500_000,    # Rs 5,000
        "yearly_price_paisa": 5_000_000,   # Rs 50,000
        "max_branches": 5,
        "max_terminals": 10,
        "max_products": 10000,
        "max_users": 15,
        "features": {
            "fbr_integration": True,
            "csv_import": True,
            "reports": "full",
            "support": "phone",
            "scheduled_reports": True,
            "loyalty_basic": True,
        },
        "sort_order": 2,
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Custom — contact sales for pricing. Unlimited everything + dedicated support.",
        "monthly_price_paisa": 1_500_000,  # Rs 15,000 (starting; negotiated)
        "yearly_price_paisa": 15_000_000,  # Rs 150,000
        "max_branches": None,
        "max_terminals": None,
        "max_products": None,
        "max_users": None,
        "features": {
            "fbr_integration": True,
            "csv_import": True,
            "reports": "full",
            "support": "dedicated",
            "scheduled_reports": True,
            "loyalty_full": True,
            "white_label_lite": True,
            "custom_workflows": True,
        },
        "sort_order": 3,
    },
]


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("platform_admin", "SubscriptionPlan")
    PlatformSettings = apps.get_model("platform_admin", "PlatformSettings")

    for plan in DEFAULT_PLANS:
        SubscriptionPlan.objects.update_or_create(
            code=plan["code"],
            defaults={k: v for k, v in plan.items() if k != "code"},
        )

    # Singleton — create the row if absent.
    PlatformSettings.objects.get_or_create(
        defaults={
            "platform_name": "Pakistan POS",
            "support_email": "support@pakistanpos.example.com",
            "default_trial_days": 14,
        },
    )


def unseed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("platform_admin", "SubscriptionPlan")
    SubscriptionPlan.objects.filter(
        code__in=[p["code"] for p in DEFAULT_PLANS],
    ).delete()
    # Don't delete PlatformSettings on rollback — it may have been edited.


class Migration(migrations.Migration):
    dependencies = [
        ("platform_admin", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_plans, unseed_plans),
    ]
