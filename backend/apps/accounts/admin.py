"""User admin — platform admins only.

The Users page in Django admin lists ONLY platform-staff users
(`is_platform_staff=True`). Tenant-side people (owners, managers,
cashiers) are created via the Tenant and Cashier admins under
`apps.tenants.admin` — never here. That keeps the platform-admin
flow small and focused: one form, no kind picker, no per-kind branching.

Tier 1 — Super super admin (request.user.is_superuser=True): full CRUD.
Tier 2 — Platform staff: can ADD platform admins but cannot edit/delete
         peers (only their own profile). Self-edit is always allowed.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm

from .forms import PlatformUserChangeForm, PlatformUserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """Platform admin list + create + change.

    The queryset is filtered to platform-staff users only — tenant-side
    rows never appear here.
    """

    form = PlatformUserChangeForm
    add_form = PlatformUserCreationForm
    change_password_form = AdminPasswordChangeForm

    class Media:
        css = {"all": ("accounts/admin/admin_forms.css",)}

    warn_unsaved_form = True
    list_fullwidth = True
    ordering = ("email",)
    # Renders our role-hint banner above the User change form. Unfold
    # iframes this template after the <form> opens and before the
    # fieldsets, so banner styling stays self-contained.
    change_form_before_template = "accounts/admin/role_hint_banner.html"
    list_display = (
        "email", "full_name", "platform_role_badge",
        "is_active", "bundles_summary", "last_login",
    )
    list_filter = ("platform_role", "is_active")
    search_fields = ("email", "full_name", "phone")

    # --- Restrict queryset to platform staff ------------------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(is_platform_staff=True)

    # --- Fieldsets -------------------------------------------------------
    fieldsets = (
        (None, {"fields": ("email", "password_reset_link")}),
        (_("Personal info"), {
            "fields": ("full_name", "phone", "preferred_language"),
        }),
        (_("Role + permissions"), {
            "fields": ("platform_role", "permission_bundles"),
            "description": (
                "Role is the label; bundles are what they can actually "
                "do. Tick the bundles this operator needs."
            ),
        }),
        (_("Account state"), {"fields": ("is_active",)}),
        (_("Activity (support triage)"), {
            "classes": ("collapse",),
            "fields": ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until"),
        }),
    )
    add_fieldsets = (
        ("Identity", {
            "classes": ("wide",),
            "fields": ("email", "full_name", "phone"),
        }),
        ("Password", {
            "classes": ("wide",),
            "fields": ("password1", "password2"),
            "description": "Used to sign in to this admin site.",
        }),
        ("Role + permissions", {
            "classes": ("wide",),
            "fields": ("platform_role", "permission_bundles"),
            "description": (
                "Pick the role label and tick the bundles the operator "
                "needs. You can refine permissions later on the user's "
                "edit page."
            ),
        }),
        ("Account state", {
            "classes": ("wide",),
            "fields": ("is_active",),
        }),
    )

    readonly_fields = (
        "last_login", "password_changed_at",
        "failed_login_count", "locked_until",
        "password_reset_link",
    )

    # --- Form wiring (pass request_user into both forms) ------------------
    def get_form(self, request, obj=None, change=False, **kwargs):
        FormCls = super().get_form(request, obj, change=change, **kwargs)

        # The Account Manager '+' popup on the Tenant form passes
        # `?platform_role=account_manager` to this view. When present on
        # the GET (or POST resubmit), pre-fill the platform_role field
        # so the operator doesn't have to remember which role to pick.
        # Validated against the model's choices so a tampered URL can
        # only set a known role.
        valid_roles = {k for k, _ in User._meta.get_field("platform_role").choices}
        initial_role = (
            request.GET.get("platform_role")
            or request.POST.get("platform_role")
            or ""
        )
        if initial_role not in valid_roles:
            initial_role = ""

        class _BoundForm(FormCls):
            def __init__(self, *args, **inner_kwargs):
                inner_kwargs["request_user"] = request.user
                if initial_role and not change:
                    inner_kwargs.setdefault("initial", {})
                    inner_kwargs["initial"].setdefault(
                        "platform_role", initial_role,
                    )
                super().__init__(*args, **inner_kwargs)

        return _BoundForm

    def add_view(self, request, form_url="", extra_context=None):
        """Inject a yellow banner when the form was opened via the
        Account Manager '+' popup on the Tenant form (or, more broadly,
        whenever ?platform_role=... is present). Makes it obvious that
        this is a platform-admin creation flow, not a one-off Account
        Manager record."""
        valid_roles = {k for k, _ in User._meta.get_field("platform_role").choices}
        role_hint = (request.GET.get("platform_role") or "").strip()
        ctx = dict(extra_context or {})
        if role_hint in valid_roles:
            role_label = dict(User._meta.get_field("platform_role").choices)[role_hint]
            ctx["popup_role_banner"] = (
                f"You're creating a new <strong>{role_label}</strong>. "
                f"This is a platform-staff (super-admin team) user — "
                f"they sign in to this admin site, not to admin-web."
            )
        return super().add_view(request, form_url=form_url, extra_context=ctx)

    # Same UX principle as TenantAdmin / CashierAdmin: one form, one
    # "Save" button, return to the list. No "Save and continue editing"
    # or "Save and add another" — the platform-admin form is complete in
    # one shot.
    def render_change_form(self, request, context, add=False, change=False,
                           form_url="", obj=None):
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(
            request, context, add=add, change=change,
            form_url=form_url, obj=obj,
        )

    def response_add(self, request, obj, post_url_continue=None):
        """Skip the edit-page detour after create; go to the list. The
        '?platform_role=...' popup flow (Account Manager '+') is handled
        by Django's own _popup machinery and is NOT affected by this
        override — popup adds still close the window + bubble the new
        FK back to the opener.
        """
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        # Preserve popup behavior — Django's super() handles _popup
        # correctly (sends back the JS that closes the window).
        if request.GET.get("_popup") or request.POST.get("_popup"):
            return super().response_add(
                request, obj, post_url_continue=post_url_continue,
            )
        return HttpResponseRedirect(
            reverse("admin:accounts_user_changelist",
                    current_app=self.admin_site.name),
        )

    # --- Display helpers -------------------------------------------------

    @admin.display(description="Password")
    def password_reset_link(self, obj):
        if not obj or not obj.pk:
            return mark_safe(
                '<span style="opacity:.6;">Save the user first to set a password.</span>'
            )
        return format_html(
            '<a href="../password/" class="inline-flex items-center gap-1 '
            'text-primary-600 hover:underline dark:text-primary-500" '
            'style="font-size:0.85rem;">'
            '<span class="material-symbols-outlined" style="font-size:1rem;">'
            'key</span> Change password</a>'
        )

    # Per-role badge background. Lets Account Managers (and any other
    # role we want to surface visually) stand out from the generic
    # purple platform-staff pill. Keys = platform_role; values = (bg, fg).
    _ROLE_BADGE_COLORS = {
        "super_admin":         ("#dc2626", "white"),   # red
        "account_manager":     ("#0284c7", "white"),   # sky-600
        "billing_admin":       ("#059669", "white"),   # emerald-600
        "support_lead":        ("#7c3aed", "white"),   # violet-600
        "support_agent":       ("#a78bfa", "white"),   # violet-400
        "sales_lead":          ("#db2777", "white"),   # pink-600
        "sales_rep":           ("#f472b6", "white"),   # pink-400
        "read_only_observer":  ("#6b7280", "white"),   # gray-500
    }

    @admin.display(description="Role", ordering="platform_role")
    def platform_role_badge(self, obj):
        if obj.is_superuser:
            bg, fg = self._ROLE_BADGE_COLORS["super_admin"]
            return format_html(
                '<span style="background:{};color:{};'
                'padding:2px 8px;border-radius:9999px;font-size:11px;'
                'font-weight:600;">Super admin</span>',
                bg, fg,
            )
        role = obj.platform_role or ""
        role_label = obj.get_platform_role_display() if role else "Platform staff"
        bg, fg = self._ROLE_BADGE_COLORS.get(role, ("#7c3aed", "white"))
        return format_html(
            '<span style="background:{};color:{};'
            'padding:2px 8px;border-radius:9999px;font-size:11px;'
            'font-weight:600;">{}</span>',
            bg, fg, role_label,
        )

    @admin.display(description="Bundles")
    def bundles_summary(self, obj):
        from .platform_perms import PLATFORM_PERMISSION_BUNDLES, bundle_perm_keys
        if obj.is_superuser:
            return format_html(
                '<span style="background:#fef3c7;color:#92400e;'
                'padding:2px 8px;border-radius:9999px;font-size:11px;'
                'font-weight:600;">All bundles (super)</span>'
            )
        held_pairs = {
            (p.content_type.app_label, p.codename)
            for p in obj.user_permissions.select_related("content_type")
        }
        held_bundles = [
            b for b in PLATFORM_PERMISSION_BUNDLES
            if bundle_perm_keys(b["key"]).issubset(held_pairs)
        ]
        if not held_bundles:
            return format_html(
                '<span style="color:#dc2626;font-size:11px;">⚠ no bundles assigned</span>'
            )
        return format_html_join(
            mark_safe(" "),
            '<span style="display:inline-block;background:#ede9fe;'
            'color:#5b21b6;font-size:10px;padding:1px 6px;border-radius:9999px;'
            'font-weight:500;margin:1px 2px;" title="{}">{}</span>',
            ((b["description"], b["label"]) for b in held_bundles),
        )

    # --- Filter `user_permissions` queryset (advanced widget) -------------

    _HIDDEN_APP_LABELS = frozenset({
        "contenttypes", "token_blacklist", "admin", "sessions",
    })
    _HIDDEN_MODELS = frozenset({
        ("reports", "dailysalessummary"),
        ("reports", "productvelocity"),
        ("reports", "reportrun"),
        ("reports", "reportfavorite"),
        ("sync", "synclog"),
        ("customers", "customerledger"),
        ("sales", "saleitemhistory"),
        ("auth", "permission"),
    })

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == "user_permissions":
            qs = kwargs.get("queryset") or db_field.remote_field.model.objects
            qs = qs.exclude(content_type__app_label__in=self._HIDDEN_APP_LABELS)
            for app_label, model_name in self._HIDDEN_MODELS:
                qs = qs.exclude(
                    content_type__app_label=app_label,
                    content_type__model=model_name,
                )
            kwargs["queryset"] = qs.select_related("content_type")
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    # --- Permission tiers -------------------------------------------------

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None:
            return True
        if request.user.is_superuser:
            return True
        # Self-edit always allowed.
        if obj.pk == request.user.pk:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    # --- Safe delete (last-owner guard surfaces as flash + redirect) -----

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
            messages.error(request, msg)
            return HttpResponseRedirect(
                reverse(
                    f"admin:{self.opts.app_label}_{self.opts.model_name}_change",
                    args=[object_id],
                ),
            )

    def delete_queryset(self, request, queryset):
        blocked, deleted = [], 0
        for user in queryset:
            try:
                user.delete()
                deleted += 1
            except ValidationError as e:
                msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
                blocked.append(f"{user.email}: {msg}")
        if deleted:
            messages.success(
                request, f"Deleted {deleted} user{'s' if deleted != 1 else ''}.",
            )
        for line in blocked:
            messages.error(request, line)
