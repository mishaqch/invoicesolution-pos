from django.apps import AppConfig


class FbrConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fbr"
    label = "fbr"

    def ready(self) -> None:
        from . import signals  # noqa: F401
