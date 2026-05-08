from django.contrib import admin

from .models import Tenant, TenantMembership


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
