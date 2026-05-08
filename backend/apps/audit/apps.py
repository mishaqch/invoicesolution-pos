from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Reserved for the audit_log model. Lands in Phase 2."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
