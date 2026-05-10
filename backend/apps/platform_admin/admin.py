"""Django admin for platform-admin models.

This is the primary control surface during V1 (before the dedicated
platform-web React app lands in Phase 9). The intent is "good enough
for a small team to run the SaaS business manually" — usage counts,
prominent fields, no fluff.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import PlatformSettings, Subscription, SubscriptionPlan


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(ModelAdmin):
    """Singleton — refuse a second row."""

    fieldsets = (
        ("Branding", {"fields": ("platform_name", "support_email", "support_phone")}),
        ("Defaults", {"fields": ("default_trial_days",)}),
        ("Receiving payments (Pakistan)", {
            "fields": (
                "payment_bank_name", "payment_bank_account_title", "payment_bank_iban",
                "payment_jazzcash_business", "payment_easypaisa_business",
                "payment_raast_id",
            ),
        }),
        ("Maintenance", {"fields": ("maintenance_mode", "maintenance_message")}),
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        # Singleton: only one row ever exists. Admins edit it; never add.
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = (
        "code", "name", "monthly_price_display", "yearly_price_display",
        "max_branches", "max_terminals", "max_products", "max_users",
        "tenants_count", "is_active",
    )
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "monthly_price_paisa")

    fieldsets = (
        (None, {"fields": ("code", "name", "description", "is_active", "sort_order")}),
        ("Pricing (paisa)", {"fields": ("monthly_price_paisa", "yearly_price_paisa")}),
        ("Limits (blank = unlimited)", {
            "fields": ("max_branches", "max_terminals", "max_products", "max_users"),
        }),
        ("Features", {"fields": ("features",)}),
    )

    @admin.display(description="Monthly")
    def monthly_price_display(self, obj):
        return f"Rs {obj.monthly_price_rs:,.0f}"

    @admin.display(description="Yearly")
    def yearly_price_display(self, obj):
        return f"Rs {obj.yearly_price_rs:,.0f}"

    @admin.display(description="Tenants")
    def tenants_count(self, obj):
        return obj.subscriptions.count()


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = (
        "tenant", "plan", "status_badge", "billing_cycle",
        "trial_ends_at", "next_invoice_at", "created_at",
    )
    list_filter = ("status", "billing_cycle", "plan")
    search_fields = ("tenant__business_name", "tenant__ntn")
    autocomplete_fields = ("tenant", "plan")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {"fields": ("tenant", "plan", "status", "billing_cycle")}),
        ("Trial", {"fields": ("trial_started_at", "trial_ends_at")}),
        ("Billing period", {
            "fields": ("current_period_start", "current_period_end", "next_invoice_at"),
        }),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    # Unfold's @display(label=...) renders WCAG-AA-compliant pill badges
    # using the same color tokens as the rest of the theme. The dict maps
    # status value → Unfold's semantic color slot.
    @display(
        description="Status",
        ordering="status",
        label={
            "trial": "info",
            "active": "success",
            "past_due": "warning",
            "suspended": "danger",
            "cancelled": "",  # neutral grey
        },
    )
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()
