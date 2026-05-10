"""Read-only admin for sales records.

Super-admin uses this for support — find an invoice by number across
all tenants, see its FBR submission state, view buyer + total. Edits
must go through the API so the audit trail and FBR sync stay in
lockstep; the admin is for inspection only.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = (
        "local_invoice_number", "tenant", "branch", "invoice_date",
        "status_badge", "fbr_invoice_number", "grand_total_display",
        "buyer_name",
    )
    list_filter = ("status", "invoice_type", "buyer_registration_type")
    search_fields = (
        "local_invoice_number", "fbr_invoice_number",
        "buyer_name", "buyer_ntn_cnic", "tenant__business_name",
    )
    autocomplete_fields = ("tenant", "branch", "terminal", "cashier", "customer")
    date_hierarchy = "invoice_date"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    @display(
        description="Status",
        ordering="status",
        label={
            "pending_sync": "info",
            "submitted": "info",
            "valid": "success",
            "finalized": "success",
            "failed": "danger",
            "edited": "warning",
            "partially_edited": "warning",
            "cancelled": "",  # neutral grey
            "partially_cancelled": "",
            "partially_edited_and_cancelled": "",
        },
    )
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @admin.display(description="Total", ordering="grand_total")
    def grand_total_display(self, obj):
        return f"Rs {obj.grand_total:,.2f}"
