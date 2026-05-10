from django.apps import AppConfig


class PlatformAdminConfig(AppConfig):
    """Platform / control-plane app — distinct from `tenants` (which models
    the shop/business). Holds Subscription, SubscriptionPlan, PlatformSettings
    + extends User and Tenant for platform-staff distinction.

    Named `platform_admin` (not just `platform`) because `platform` is a
    Python stdlib module — using it as a top-level package would risk
    import shadowing.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform_admin"
    label = "platform_admin"
