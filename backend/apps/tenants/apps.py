from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    label = "tenants"

    def ready(self) -> None:
        # Register the tenant-scoping system check.
        from . import checks  # noqa: F401
