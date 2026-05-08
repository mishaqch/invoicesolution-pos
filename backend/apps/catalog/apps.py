from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"

    def ready(self) -> None:
        # Connect signal handlers (tax-rate seed on tenant create).
        from . import signals  # noqa: F401
