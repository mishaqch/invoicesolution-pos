"""Base Django settings shared by dev / prod / test.

Layered settings:
  - base.py  — defaults, all the structure.
  - dev.py   — DEBUG, permissive CORS/hosts, console email.
  - prod.py  — strict, secure cookies, structured logging.
  - test.py  — fast Argon2, in-memory caches.

Env vars are read via django-environ (see PLAN §4 for the choice rationale).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths + env
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # → backend/

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
)
# .env file (only read when present; in compose env vars are set directly)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-base-not-for-prod")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# FBR token encryption key. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# In dev / tests, falls back to a deterministic key derived from SECRET_KEY
# so the test suite is reproducible without forcing every dev to set the var.
FBR_FERNET_KEY = env("FBR_FERNET_KEY", default="")

# Absolute base URL for links minted outside a live request (e.g. share links
# generated in a Celery task or email). When a request is available, the
# request host is used instead. Set to the tenant app origin in prod.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="")

# FBR SDC (Sale Data Controller / IMS Fiscalization Service) base URL. When set
# (e.g. http://<windows-sdc-host>:8524), POS invoices for branches with a POS ID
# are fiscalized through the SDC instead of the direct DI-API. Empty => DI-API
# path only. The SDC is a Windows service installed centrally; one SDC serves
# many POS IDs (POSID is per-invoice). See apps/fbr/sdc_client.py.
FBR_SDC_BASE_URL = env("FBR_SDC_BASE_URL", default="")

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Modern admin theme — must be listed BEFORE django.contrib.admin so its
    # templates take precedence. See UNFOLD config block below for the
    # branding + sidebar nav.
    "unfold",
    "unfold.contrib.filters",        # better filter widgets (range, dropdown)
    "unfold.contrib.forms",          # styled form widgets (mask, file picker)
    "unfold.contrib.import_export",  # noop unless django-import-export added
    "unfold.contrib.guardian",       # noop unless django-guardian added
    "unfold.contrib.simple_history", # noop unless django-simple-history added
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",          # ArrayField etc.
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Local — Phase 0
    "apps.tenants",
    "apps.accounts",
    # Local — Phase 1
    "apps.catalog",
    "apps.inventory",
    "apps.notifications",
    # Procurement (pharmacy / wholesale) — suppliers + goods receipts
    "apps.suppliers",
    "apps.purchases",
    # Restaurant / F&B vertical — tables, modifiers, kitchen
    "apps.restaurant",
    # Local — Phase 2
    "apps.customers",
    "apps.sales",
    "apps.audit",
    # Local — Phase 3
    "apps.sync",
    # Local — Phase 4
    "apps.fbr",
    # Local — Phase 5
    "apps.payments",
    # Local — Phase 6
    "apps.returns",
    # Local — Phase 7
    "apps.reports",
    # Phase 0 platform stub (control plane — separate from tenants)
    "apps.platform_admin",
    # Public marketing-site lead capture (invoicesolution.pk contact form)
    "apps.leads",
]

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom: must run AFTER auth middleware so request.user is populated.
    "apps.tenants.middleware.TenantContextMiddleware",
    # Phase 8 — structured request log (last so it sees the resolved
    # tenant_id and user). Skips /api/health and static.
    "core.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-level template overrides (e.g. admin/base_site.html, which
        # injects a top loading bar + submit spinners into the super-admin so
        # navigation never feels dead on a slow link). Listed before APP_DIRS
        # lookups so it wins over the packaged admin/unfold templates.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database + cache
# ---------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://pos:pos_dev_password@localhost:5432/pos",
    ),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

CACHES = {
    "default": env.cache(
        "REDIS_URL",
        default="redis://localhost:6379/0",
        backend="django.core.cache.backends.redis.RedisCache",
    ),
}

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = False

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

# Argon2id is the default. PBKDF2 retained as a legacy fallback only.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# JWT — 15 min access / 7 day refresh, with rotation + blacklist (PROJECT_PLAN §10).
SIMPLE_JWT = {
    # Long enough to cover a full working shift without surprise logouts.
    # A 15-min access token forced a refresh every 15 min; any hiccup in the
    # rotate/blacklist dance logged the user out mid-work. A 12h access token
    # is a reasonable security/UX balance for a POS, and the 30-day refresh
    # gives a smooth "stay signed in" experience.
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    # Rotation + blacklist caused premature logouts: with multiple tabs / the
    # POS terminal + admin-web sharing a session, concurrent refreshes would
    # rotate the token one client still held, blacklisting it → instant
    # logout. Disable rotation; the access-token expiry is the security
    # boundary. (Logout still works via the client clearing its tokens.)
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.PosTokenObtainPairSerializer",
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Custom: same PageNumberPagination but honours ?page_size=N (capped at
    # max_page_size) so list UIs can offer a rows-per-page control.
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # PROJECT_PLAN §10 calls for "5 attempts / 15 min / IP". DRF's built-in
        # throttle window is fixed (s|m|h|d), so we approximate with 20/h
        # which averages to ~5 per 15 min and gracefully bursts. A custom
        # SlidingWindowThrottle can land later if we need exactness.
        "auth": "20/h",
        # Public marketing-site contact form — generous enough for a genuine
        # visitor, tight enough to blunt spam bursts from one IP.
        "leads": "10/h",
    },
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}

# ---------------------------------------------------------------------------
# i18n / tz
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en"
TIME_ZONE = env("TIME_ZONE", default="Asia/Karachi")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Email (SMTP from env — used for marketing-site lead notifications)
# ---------------------------------------------------------------------------
# Wire any transactional provider (Brevo/Resend/Mailgun/Gmail) via env. When
# EMAIL_HOST is unset we fall back to console (dev) / a no-op log (prod) so a
# missing config never breaks the request — leads still persist to the DB and
# show in the super-admin. dev.py overrides EMAIL_BACKEND to console.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="InvoiceSolution <noreply@invoicesolution.pk>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Where marketing-site leads are emailed. Comma-separated env list; if empty,
# leads are captured in the DB / super-admin only (no email sent).
LEADS_NOTIFY_EMAILS = env.list("LEADS_NOTIFY_EMAILS", default=[])
# Use real SMTP only when a host is configured; otherwise log to console so the
# app never errors on a missing mail server.
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}

# ---------------------------------------------------------------------------
# Django Unfold — modern admin theme
# ---------------------------------------------------------------------------
#
# Tailwind-based theme that wraps the stock Django admin. We keep the
# Django-admin URL surface and ModelAdmin classes, but every page picks
# up Unfold's template + sidebar.
#
# WCAG 2.2 AA notes:
#  - Color tokens below resolve to a Tailwind palette with ≥4.5:1 contrast
#    in both light and dark mode (Unfold's defaults already meet this).
#  - SHOW_HISTORY + SHOW_VIEW_ON_SITE are off because they introduce
#    decorative chrome we don't need on a single-tenant control plane.
#  - "BORDER_RADIUS" set to a small value so focus-visible rings don't
#    look smeared on rounded buttons.
#
UNFOLD = {
    "SITE_TITLE": "POS System — Super Admin",
    "SITE_HEADER": "POS System",
    "SITE_SUBHEADER": "Platform control plane",
    # No "Return to site" link — this Django app is super-admin only,
    # there's no public-facing site at /. Setting SITE_URL to None
    # hides Unfold's back-arrow link in the top-right of the admin
    # chrome. (The React tenant admin lives on a separate host:port
    # and isn't accessible via this link.)
    "SITE_URL": None,
    "SITE_SYMBOL": "storefront",          # Material icon shown in sidebar
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "THEME": None,                         # None = user toggle (light/dark)
    "BORDER_RADIUS": "6px",
    "STYLES": [
        # Layered after Unfold's own bundle so we can tighten WCAG-relevant
        # bits (focus rings, reduced motion, forced-colors).
        lambda request: "/static/admin-extra/wcag.css",
    ],
    "COLORS": {
        # Brand green — slightly desaturated so contrast against white
        # in headings stays ≥4.5:1.
        "primary": {
            "50": "240 253 244",
            "100": "220 252 231",
            "200": "187 247 208",
            "300": "134 239 172",
            "400": "74 222 128",
            "500": "34 197 94",
            "600": "22 163 74",
            "700": "21 128 61",
            "800": "22 101 52",
            "900": "20 83 45",
            "950": "5 46 22",
        },
    },
    # Sidebar nav. Each section and each item carries a "permission"
    # callback (dotted path resolved by Unfold via import_string). The
    # callback receives `request` and returns True/False — False hides
    # the row. Without these, a delegated platform_admin who only has
    # User+Tenant+Billing bundles would still see "Operations" (FBR /
    # invoices / audit) in the nav and get 403 on click.
    #
    # Callbacks live in core/admin_nav_perms.py and short-circuit to
    # True for is_superuser.
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Overview",
                "separator": False,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": "/admin/",
                    },
                ],
            },
            {
                "title": "Tenants",
                "separator": True,
                "permission": "core.admin_nav_perms.tenants_section",
                "items": [
                    {
                        "title": "Tenants",
                        "icon": "domain",
                        "link": "/admin/tenants/tenant/",
                        "permission": "core.admin_nav_perms.view_tenant",
                    },
                    {
                        "title": "Branches",
                        "icon": "store",
                        "link": "/admin/tenants/branch/",
                        "permission": "core.admin_nav_perms.view_branch",
                    },
                    {
                        "title": "Terminals",
                        "icon": "point_of_sale",
                        "link": "/admin/tenants/terminal/",
                        "permission": "core.admin_nav_perms.view_terminal",
                    },
                    {
                        "title": "Cashiers",
                        "icon": "badge",
                        "link": "/admin/tenants/cashier/",
                        "permission": "core.admin_nav_perms.view_cashier",
                    },
                ],
            },
            {
                "title": "Billing",
                "separator": True,
                "permission": "core.admin_nav_perms.billing_section",
                "items": [
                    {
                        "title": "Subscription plans",
                        "icon": "workspace_premium",
                        "link": "/admin/platform_admin/subscriptionplan/",
                        "permission": "core.admin_nav_perms.view_subscription_plan",
                    },
                    {
                        "title": "Subscriptions",
                        "icon": "subscriptions",
                        "link": "/admin/platform_admin/subscription/",
                        "permission": "core.admin_nav_perms.view_subscription",
                    },
                    {
                        "title": "Platform settings",
                        "icon": "tune",
                        "link": "/admin/platform_admin/platformsettings/",
                        "permission": "core.admin_nav_perms.view_platform_settings",
                    },
                ],
            },
            {
                "title": "People",
                "separator": True,
                "permission": "core.admin_nav_perms.people_section",
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": "/admin/accounts/user/",
                        "permission": "core.admin_nav_perms.view_user",
                    },
                    {
                        "title": "Groups",
                        "icon": "groups",
                        "link": "/admin/auth/group/",
                        "permission": "core.admin_nav_perms.view_group",
                    },
                ],
            },
            {
                "title": "Operations",
                "separator": True,
                "permission": "core.admin_nav_perms.operations_section",
                "items": [
                    {
                        "title": "FBR submissions",
                        "icon": "send",
                        "link": "/admin/fbr/fbrsubmission/",
                        "permission": "core.admin_nav_perms.view_fbr_submission",
                    },
                    {
                        "title": "FBR tokens",
                        "icon": "vpn_key",
                        "link": "/admin/fbr/fbrtoken/",
                        "permission": "core.admin_nav_perms.view_fbr_token",
                    },
                    {
                        "title": "Invoices",
                        "icon": "receipt_long",
                        "link": "/admin/sales/invoice/",
                        "permission": "core.admin_nav_perms.view_invoice",
                    },
                    {
                        "title": "Audit log",
                        "icon": "fact_check",
                        "link": "/admin/audit/auditlog/",
                        "permission": "core.admin_nav_perms.view_audit_log",
                    },
                ],
            },
        ],
    },
    "TABS": [],
}
