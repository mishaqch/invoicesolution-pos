"""Read-only admin for customer records.

Support staff use this to look up walk-in vs registered buyer
metadata, never to mutate it. Customer changes flow through the
tenant API so the audit log records who/when.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Customer, CustomerGroup


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ("name", "tenant", "ntn", "cnic",
                    "phone", "registration_type", "is_active", "created_at")
    list_filter = ("registration_type", "is_active", "province")
    search_fields = ("name", "ntn", "cnic", "phone", "email",
                     "tenant__business_name")
    autocomplete_fields = ("tenant",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


@admin.register(CustomerGroup)
class CustomerGroupAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ("name", "tenant", "default_discount_pct")
    search_fields = ("name", "tenant__business_name")
    autocomplete_fields = ("tenant",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
