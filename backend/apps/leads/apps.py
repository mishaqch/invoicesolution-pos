from django.apps import AppConfig


class LeadsConfig(AppConfig):
    """Public marketing-site leads (contact / book-a-demo form)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"
    label = "leads"
