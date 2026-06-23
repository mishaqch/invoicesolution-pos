from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    """Triage marketing-site leads. The super-admin list IS the lead inbox —
    even if email notifications aren't configured, every lead lands here."""

    list_display = (
        "business_name",
        "name",
        "phone",
        "product_interest",
        "city",
        "handled",
        "created_at",
    )
    list_filter = ("handled", "product_interest", "business_type", "created_at")
    search_fields = ("business_name", "name", "phone", "email", "city", "message")
    list_editable = ("handled",)
    readonly_fields = (
        "id",
        "source",
        "ip",
        "user_agent",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    list_per_page = 50

    fieldsets = (
        ("Contact", {"fields": ("name", "business_name", "phone", "email", "city")}),
        ("Interest", {"fields": ("business_type", "product_interest", "message")}),
        ("Triage", {"fields": ("handled",)}),
        ("Provenance", {"fields": ("source", "ip", "user_agent", "created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        # Leads come from the public form, not hand-entry.
        return False
