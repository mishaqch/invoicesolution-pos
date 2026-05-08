from django.apps import AppConfig


class SyncConfig(AppConfig):
    """Reserved for the sync_log model + sync API. Lands in Phase 3."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync"
    label = "sync"
