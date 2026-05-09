from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
    label = "reports"

    def ready(self):
        from . import signals  # noqa: F401
        from . import reports  # noqa: F401  # registers every report via @register
