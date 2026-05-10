"""Read-only admin for the immutable audit log.

The DB rejects UPDATE/DELETE on audit_log via REVOKE (migration 0002);
this admin matches that posture by making every field readonly and
disabling add + delete. Use it to investigate a specific entity's
history (entity_type + entity_id filter) or a user's actions.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ("created_at", "tenant", "user", "entity_type",
                    "entity_id", "action")
    list_filter = ("entity_type", "action")
    search_fields = (
        "entity_id", "tenant__business_name",
        "user__email", "user__full_name",
    )
    autocomplete_fields = ("tenant", "user")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
