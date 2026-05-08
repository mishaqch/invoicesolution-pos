from django.contrib import admin

from .models import Branch, Tenant, TenantMembership, Terminal


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("business_name", "ntn", "business_type", "province",
                    "subscription_status", "created_at")
    search_fields = ("business_name", "ntn", "strn")
    list_filter = ("business_type", "province", "subscription_plan", "subscription_status")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active", "created_at")
    search_fields = ("tenant__business_name", "user__email", "user__full_name")
    list_filter = ("role", "is_active")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant", "user")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tenant", "city", "province", "is_active", "is_default")
    search_fields = ("name", "code", "tenant__business_name", "city")
    list_filter = ("province", "is_active", "is_default")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant",)


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "tenant", "is_active", "last_seen_at")
    search_fields = ("name", "device_fingerprint", "branch__name")
    list_filter = ("is_active", "customer_display_enabled")
    readonly_fields = ("id", "created_at", "updated_at", "last_seen_at", "last_synced_at")
    autocomplete_fields = ("tenant", "branch")
