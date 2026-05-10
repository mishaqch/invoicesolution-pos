from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "is_active",
                     "is_platform_staff", "platform_role", "is_staff", "last_login")
    list_filter = ("is_active", "is_platform_staff", "platform_role",
                    "is_staff", "is_superuser", "preferred_language")
    search_fields = ("email", "full_name", "phone")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("full_name", "phone", "preferred_language")}),
        (_("PIN"), {"fields": ("pin_hash",)}),
        (_("Platform staff (control plane)"), {
            "fields": ("is_platform_staff", "platform_role"),
            "description": (
                "Set when this user works for the SaaS operator, not a tenant. "
                "Platform staff are blocked from tenant API endpoints unless "
                "mid-impersonation (Phase 9 feature)."
            ),
        }),
        (_("Permissions (Django)"), {
            "fields": ("is_active", "is_staff", "is_superuser",
                       "groups", "user_permissions"),
        }),
        (_("Activity"), {"fields": ("last_login", "password_changed_at",
                                     "failed_login_count", "locked_until")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "password1", "password2",
                       "is_staff", "is_active"),
        }),
    )
    readonly_fields = ("last_login", "password_changed_at", "pin_hash")
