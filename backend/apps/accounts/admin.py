"""User admin — opinionated about the platform-staff vs tenant-user split.

The Django stock User admin exposes 200+ row-level permission checkboxes
plus the Groups widget plus is_staff / is_superuser flags. For TENANT
users (cashiers, owners, accountants — the people working FOR the
businesses we host), none of that machinery applies — their permissions
come from their TenantMembership.role, not from Django's row-perm system.

This admin hides the noisy machinery for tenant users, surfaces the
tenant-membership inline directly on the user change form (so operators
edit role on the same page as the user), and shows a plain-English
summary of what each role unlocks below the dropdown.

Platform-staff users (super-admin operators) still see the full Django
permission machinery — they need it to access the Django admin pages.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.accounts.permissions import (
    ROLE_DESCRIPTIONS,
    all_perms_for_role,
    role_description,
)
from apps.tenants.models import TenantMembership

from .models import User


class TenantMembershipInline(TabularInline):
    """Edit the user's tenant memberships directly on the User form.

    Without this, super-admin operators have to bounce to
    Tenants → Tenant memberships, find the row, and edit it there.
    Most of the time the user has exactly one membership, so showing
    it inline makes the whole onboarding flow click → save on a single
    screen.
    """

    model = TenantMembership
    extra = 1  # Show one empty row by default so creating a new user
              # naturally invites the operator to add a membership.
    autocomplete_fields = ("tenant",)
    fields = ("tenant", "role", "is_active", "role_summary")
    readonly_fields = ("role_summary",)

    @admin.display(description="What this role can do")
    def role_summary(self, obj):
        """Plain-English description of the role's permissions. Updates
        when the row is saved with a new role.

        New rows (no pk yet) show a helper hint instead of a description
        since we don't know the role yet."""
        if not obj or not obj.role:
            return mark_safe(
                '<span style="opacity:0.6;font-size:11px;">'
                'Pick a role + save to see what it unlocks.</span>',
            )
        desc = role_description(obj.role)
        perms = all_perms_for_role(obj.role)
        perm_chips = "".join(
            f'<span style="display:inline-block;background:#e5e7eb;'
            f'color:#1f2937;font-family:ui-monospace,monospace;'
            f'font-size:10px;padding:1px 6px;margin:1px 3px 1px 0;'
            f'border-radius:9999px;">{p}</span>'
            for p in perms
        )
        return format_html(
            '<div style="font-size:12px;line-height:1.4;max-width:500px;">'
            '<p style="margin:0 0 6px;">{}</p>'
            '<div>{}</div>'
            '</div>',
            desc,
            mark_safe(perm_chips),
        )


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    warn_unsaved_form = True
    list_fullwidth = True
    ordering = ("email",)
    list_display = (
        "email", "full_name",
        "is_active",
        "user_type_badge",
        "membership_summary",
        "last_login",
    )
    list_filter = ("is_active", "is_platform_staff", "platform_role",
                    "preferred_language")
    search_fields = ("email", "full_name", "phone")
    inlines = [TenantMembershipInline]

    # Standard sets we use to slice the change form by user type.
    _PLATFORM_FIELDSETS = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {
            "fields": ("full_name", "phone", "preferred_language"),
        }),
        (_("Platform staff (control plane)"), {
            "fields": ("is_platform_staff", "platform_role"),
            "description": (
                "This user works for the SaaS platform, not for a "
                "tenant. They sign in at /admin/ and are blocked from "
                "every tenant API endpoint."
            ),
        }),
        (_("Django permissions"), {
            "fields": ("is_active", "is_staff", "is_superuser",
                       "groups", "user_permissions"),
            "description": (
                "Standard Django row-level permissions. Only relevant "
                "for platform-staff users — controls which Django "
                "admin pages they can see / edit. Tenant users get "
                "their permissions from the TenantMembership role "
                "shown in the inline below."
            ),
        }),
        (_("Activity"), {
            "fields": ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until"),
        }),
    )
    _TENANT_FIELDSETS = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {
            "fields": ("full_name", "phone", "preferred_language"),
        }),
        (_("PIN"), {
            "fields": ("pin_hash",),
            "description": "Cashier's terminal-PIN for quick re-auth.",
        }),
        (_("Access"), {
            "fields": ("is_active",),
            "description": (
                "Tenant users always have is_staff=False (no Django "
                "admin access) and is_platform_staff=False (this is "
                "a tenant user, not a platform operator). Their "
                "actual permissions come from the tenant membership "
                "role shown below — pick a role there, save, and the "
                "user can do whatever that role allows."
            ),
        }),
        (_("Activity"), {
            "fields": ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until"),
        }),
    )

    # Add (create) form — minimal. is_staff stays off by default.
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "password1", "password2",
                       "is_active"),
            "description": (
                "Creates a tenant user by default (is_staff=False, "
                "is_platform_staff=False, is_active=True). After "
                "saving, add a Tenant membership in the inline that "
                "appears, OR tick 'Is platform staff' on the change "
                "form to promote to super-admin."
            ),
        }),
    )

    readonly_fields = (
        "last_login", "password_changed_at", "pin_hash",
        "failed_login_count", "locked_until",
    )

    def get_fieldsets(self, request, obj=None):
        """Use the platform fieldset for platform-staff users, the
        tenant fieldset for everyone else. New users (obj is None)
        go through add_fieldsets via Django's base class."""
        if obj is None:
            return self.add_fieldsets
        if obj.is_platform_staff or obj.is_superuser:
            return self._PLATFORM_FIELDSETS
        return self._TENANT_FIELDSETS

    def get_inline_instances(self, request, obj=None):
        """Hide the tenant-membership inline on the create form
        (the user doesn't have a pk yet, so the inline would fail
        to save) and on platform-staff users (they shouldn't have
        any memberships).
        """
        if obj is None or obj.is_platform_staff:
            return []
        return super().get_inline_instances(request, obj)

    # ----- List display helpers ---------------------------------------

    @admin.display(description="Type", ordering="is_platform_staff")
    def user_type_badge(self, obj):
        if obj.is_platform_staff:
            return format_html(
                '<span style="background:#7c3aed;color:white;'
                'padding:2px 8px;border-radius:9999px;font-size:11px;'
                'font-weight:600;">Platform staff</span>',
            )
        return format_html(
            '<span style="background:#16a34a;color:white;'
            'padding:2px 8px;border-radius:9999px;font-size:11px;'
            'font-weight:600;">Tenant user</span>',
        )

    @admin.display(description="Tenant(s) / role")
    def membership_summary(self, obj):
        """Compact list of this user's tenants + roles, shown in the
        user list. Catches the 'forgot to add membership' bug at a
        glance — the cell is empty for users with no membership."""
        if obj.is_platform_staff:
            return format_html('<span style="opacity:0.5;">—</span>')
        memberships = list(
            TenantMembership.objects.filter(user=obj, is_active=True)
            .select_related("tenant")
            .order_by("tenant__business_name")
        )
        if not memberships:
            return format_html(
                '<span style="color:#dc2626;font-size:11px;">'
                '⚠ no active membership</span>',
            )
        return format_html_join(
            mark_safe("<br>"),
            '<span style="font-size:12px;"><strong>{}</strong> '
            '<em style="opacity:0.7;">({})</em></span>',
            ((m.tenant.business_name, m.role) for m in memberships),
        )
