"""Read-only admin for FBR operational records.

Super-admin staff use these for support triage — find a tenant's
submission by invoice ref, see why a row failed PRAL validation,
inspect the encrypted token row exists. Editing is disabled by
design: PRAL is the source of truth, mutating these rows from the
admin would desync the audit trail.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import FbrCancelBudget, FbrScenarioTest, FbrSubmission, FbrToken


class _ReadOnlyAdmin(ModelAdmin):
    list_fullwidth = True

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


@admin.register(FbrToken)
class FbrTokenAdmin(_ReadOnlyAdmin):
    list_display = ("tenant", "environment", "is_active", "created_at", "updated_at")
    list_filter = ("environment", "is_active")
    search_fields = ("tenant__business_name", "tenant__ntn")
    autocomplete_fields = ("tenant",)


@admin.register(FbrSubmission)
class FbrSubmissionAdmin(_ReadOnlyAdmin):
    list_display = (
        "invoice", "tenant", "endpoint", "http_status_badge",
        "status_code", "fbr_invoice_number", "attempt_number", "submitted_at",
    )
    list_filter = ("environment", "endpoint")
    search_fields = (
        "invoice__local_invoice_no", "fbr_invoice_number",
        "tenant__business_name", "status_code",
    )
    autocomplete_fields = ("tenant",)
    date_hierarchy = "submitted_at"

    @display(description="HTTP", ordering="http_status",
             label={"2": "success", "4": "warning", "5": "danger"})
    def http_status_badge(self, obj):
        if obj.http_status is None:
            return "", "-"
        # Bucket by leading digit (2xx success / 4xx warn / 5xx danger).
        return str(obj.http_status)[0], str(obj.http_status)


@admin.register(FbrScenarioTest)
class FbrScenarioTestAdmin(_ReadOnlyAdmin):
    list_display = ("tenant", "scenario_code", "status_badge",
                    "fbr_invoice_number", "last_attempt_at")
    list_filter = ("status",)
    search_fields = ("tenant__business_name", "scenario_code")

    @display(description="Status", ordering="status",
             label={"pending": "info", "submitting": "info",
                    "success": "success", "failed": "danger"})
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()


@admin.register(FbrCancelBudget)
class FbrCancelBudgetAdmin(_ReadOnlyAdmin):
    list_display = ("tenant", "month_start", "previous_month_sales",
                    "consumed_amount")
    search_fields = ("tenant__business_name",)
    list_filter = ("month_start",)
    date_hierarchy = "month_start"
