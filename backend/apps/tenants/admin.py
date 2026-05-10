from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from .models import Branch, Tenant, TenantMembership, Terminal


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    # Unfold-specific niceties: warn-on-unsaved when leaving a form,
    # compact list rendering toggle, and inline column highlights.
    warn_unsaved_form = True
    list_fullwidth = True
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


@admin.register(TenantMembership)
class TenantMembershipAdmin(ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active", "created_at")
    search_fields = ("tenant__business_name", "user__email", "user__full_name")
    list_filter = ("role", "is_active")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant", "user")


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
