from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from .models import Branch, Tenant, TenantMembership, Terminal
from .modules import FORCED_MODULE_KEYS, MODULES, normalise as normalise_modules


class ModulesCheckboxWidget(forms.CheckboxSelectMultiple):
    """Renders the modules-enabled choices grouped by module group with
    forced modules pre-checked and disabled. Falls back to the stock
    CheckboxSelectMultiple template when the grouped one is unavailable.
    """

    template_name = "tenants/admin/modules_checkbox.html"


class ModulesField(forms.MultipleChoiceField):
    """A MultipleChoiceField backed by the module catalog. We override
    `clean` so forced modules (sales, fbr) are always included even if
    the operator unticks them — defense in depth for the UI being out
    of sync with the underlying lock.
    """

    def __init__(self, *args, **kwargs):
        choices = [(m["key"], m["label"]) for m in MODULES]
        super().__init__(*args, choices=choices, required=False, **kwargs)

    def clean(self, value):
        cleaned = super().clean(value)
        # Forced modules ride along automatically.
        return normalise_modules(cleaned)


class TenantAdminForm(forms.ModelForm):
    modules_enabled = ModulesField(
        widget=ModulesCheckboxWidget,
        help_text=(
            "Tick the modules this tenant is allowed to use. "
            "Sales and FBR are forced on (the platform's core) and "
            "stay enabled regardless of selection."
        ),
    )

    class Meta:
        model = Tenant
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-tick whatever the tenant currently has enabled. New tenants
        # get the field's initial via the model's callable default.
        if self.instance and self.instance.pk:
            self.fields["modules_enabled"].initial = list(
                self.instance.modules_enabled or [],
            )


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    # Unfold-specific niceties: warn-on-unsaved when leaving a form,
    # compact list rendering toggle, and inline column highlights.
    warn_unsaved_form = True
    list_fullwidth = True
    form = TenantAdminForm
    list_display = ("business_name", "ntn", "business_type", "province",
                    "subscription_status", "suspended_at", "signup_source",
                    "account_manager", "created_at")
    search_fields = ("business_name", "ntn", "strn")
    list_filter = ("business_type", "province", "subscription_plan",
                    "subscription_status", "signup_source")
    readonly_fields = ("id", "created_at", "updated_at",
                        "onboarding_progress_live")
    autocomplete_fields = ("account_manager",)
    fieldsets = (
        (None, {"fields": ("id", "business_name", "ntn", "strn",
                            "cnic_owner", "business_type", "province",
                            "fbr_business_natures", "fbr_sector")}),
        ("Contact", {"fields": ("address", "phone", "email", "logo_url")}),
        ("Subscription (legacy chars; authoritative model is platform_admin.Subscription)", {
            "fields": ("subscription_plan", "subscription_status",
                        "trial_ends_at", "next_billing_at"),
        }),
        ("Platform / control plane", {
            "fields": ("signup_source", "account_manager", "suspended_at",
                        "internal_notes", "tags"),
        }),
        ("Modules enabled", {
            "fields": ("modules_enabled",),
            "description": (
                "Per-tenant feature catalog. The API returns 403 on "
                "endpoints whose module is unticked here. Sales and "
                "FBR are forced on and cannot be disabled — they are "
                "the platform's core."
            ),
        }),
        ("Onboarding", {
            "fields": ("onboarding_progress_live", "onboarding_state"),
            "description": (
                "Live progress is computed from real data on every page "
                "load. The JSON below stores wizard state (dismissed_at, "
                "manual operator overrides) and is auto-mirrored from the "
                "live flags whenever the tenant's admin web pings "
                "/api/onboarding/."
            ),
        }),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Onboarding progress (live)")
    def onboarding_progress_live(self, obj):
        """Computed at render time from real models — independent of the
        onboarding_state JSON. Mirrors the four checks the React wizard
        uses, plus active terminal and product counts the operator wants
        to see for support triage."""
        from apps.catalog.models import Product
        from apps.sales.models import Invoice

        branches_count = Branch.objects.filter(
            tenant=obj, deleted_at__isnull=True,
        ).count()
        terminals_count = Terminal.objects.filter(tenant=obj).count()
        active_terminals = Terminal.objects.filter(
            tenant=obj, is_active=True,
        ).count()
        products_count = Product.objects.filter(
            tenant=obj, deleted_at__isnull=True,
        ).count()
        invoices_count = Invoice.objects.for_tenant(obj.id).count()

        def row(label, ok, detail=""):
            icon = "✅" if ok else "⏳"
            color = "#15803d" if ok else "#a16207"  # green-700 / amber-700
            return format_html(
                '<div style="margin:2px 0;color:{};">{} <strong>{}</strong>'
                '<span style="opacity:.7;margin-left:8px;">{}</span></div>',
                color, icon, label, detail,
            )

        rows = [
            row("Branch added", branches_count > 0, f"{branches_count} branch(es)"),
            row("Terminal registered",
                terminals_count > 0,
                f"{terminals_count} total / {active_terminals} active"),
            row("Product added", products_count > 0, f"{products_count} SKU(s)"),
            row("First sale recorded",
                invoices_count > 0,
                f"{invoices_count} invoice(s)"),
        ]
        # Each row is already a SafeString from format_html; concat preserves
        # safety, then wrap in the outer container without re-escaping.
        body = mark_safe("".join(str(r) for r in rows))
        return format_html(
            '<div style="font-family:system-ui,sans-serif;font-size:13px;'
            'line-height:1.5;">{}</div>',
            body,
        )

    # ------------------------------------------------------------------
    # Two-tier admin hierarchy — same rules as UserAdmin.
    #
    # Only the super super admin (is_superuser=True) can edit or
    # delete existing Tenant rows. Delegated platform staff with the
    # Tenant management bundle can ADD new tenants but cannot modify
    # or remove existing ones — onboarding flow only.
    # ------------------------------------------------------------------

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None:
            # Changelist visible to anyone with view perms; per-row
            # rejection happens when they click into a row.
            return True
        if request.user.is_superuser:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(TenantMembership)
class TenantMembershipAdmin(ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active", "created_at")
    search_fields = ("tenant__business_name", "user__email", "user__full_name")
    list_filter = ("role", "is_active")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant", "user")

    # ------------------------------------------------------------------
    # Catch the last-owner guard from TenantMembership.delete() and
    # surface it as a friendly admin message + redirect instead of a 500.
    # See UserAdmin.delete_view for the same pattern.
    # ------------------------------------------------------------------

    def delete_view(self, request, object_id, extra_context=None):
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        from django.http import HttpResponseRedirect
        from django.urls import reverse
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
        from django.contrib import messages
        from django.core.exceptions import ValidationError

        blocked, deleted = [], 0
        for obj in queryset:
            try:
                obj.delete()
                deleted += 1
            except ValidationError as e:
                msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
                blocked.append(
                    f"{obj.tenant.business_name} ({obj.role} membership): {msg}",
                )

        if deleted:
            messages.success(
                request,
                f"Deleted {deleted} membership{'s' if deleted != 1 else ''}.",
            )
        for line in blocked:
            messages.error(request, line)


@admin.register(Branch)
class BranchAdmin(ModelAdmin):
    list_display = ("name", "code", "tenant", "city", "province", "is_active", "is_default")
    search_fields = ("name", "code", "tenant__business_name", "city")
    list_filter = ("province", "is_active", "is_default")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant",)


@admin.register(Terminal)
class TerminalAdmin(ModelAdmin):
    list_display = ("name", "branch", "tenant", "is_active", "last_seen_at")
    search_fields = ("name", "device_fingerprint", "branch__name")
    list_filter = ("is_active", "customer_display_enabled")
    readonly_fields = ("id", "created_at", "updated_at", "last_seen_at", "last_synced_at")
    autocomplete_fields = ("tenant", "branch")
