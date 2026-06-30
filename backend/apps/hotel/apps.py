from django.apps import AppConfig


class HotelConfig(AppConfig):
    """Hotel / resort domain — rooms + multi-day guest folios.

    For rooms+restaurant clients (e.g. TDCP). A folio groups many daily
    charge-invoices (room nights + restaurant items) into one consolidated bill
    at checkout. Gated on the `hotel` module so restaurant-only tenants never
    see it.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hotel"
    label = "hotel"
