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
        "DIRS": [],
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
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
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
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
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
    "SITE_TITLE": "Pakistan POS — Super Admin",
    "SITE_HEADER": "Pakistan POS",
    "SITE_SUBHEADER": "Platform control plane",
    "SITE_URL": "/",
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
                "items": [
                    {
                        "title": "Tenants",
                        "icon": "domain",
                        "link": "/admin/tenants/tenant/",
                    },
                    {
                        "title": "Branches",
                        "icon": "store",
                        "link": "/admin/tenants/branch/",
                    },
                    {
                        "title": "Terminals",
                        "icon": "point_of_sale",
                        "link": "/admin/tenants/terminal/",
                    },
                ],
            },
            {
                "title": "Billing",
                "separator": True,
                "items": [
                    {
                        "title": "Subscription plans",
                        "icon": "workspace_premium",
                        "link": "/admin/platform_admin/subscriptionplan/",
                    },
                    {
                        "title": "Subscriptions",
                        "icon": "subscriptions",
                        "link": "/admin/platform_admin/subscription/",
                    },
                    {
                        "title": "Platform settings",
                        "icon": "tune",
                        "link": "/admin/platform_admin/platformsettings/",
                    },
                ],
            },
            {
                "title": "People",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": "/admin/accounts/user/",
                    },
                    {
                        "title": "Groups",
                        "icon": "groups",
                        "link": "/admin/auth/group/",
                    },
                ],
            },
            {
                "title": "Operations",
                "separator": True,
                "items": [
                    {
                        "title": "FBR submissions",
                        "icon": "send",
                        "link": "/admin/fbr/fbrsubmission/",
                    },
                    {
                        "title": "FBR tokens",
                        "icon": "vpn_key",
                        "link": "/admin/fbr/fbrtoken/",
                    },
                    {
                        "title": "Invoices",
                        "icon": "receipt_long",
                        "link": "/admin/sales/invoice/",
                    },
                    {
                        "title": "Audit log",
                        "icon": "fact_check",
                        "link": "/admin/audit/auditlog/",
                    },
                ],
            },
        ],
    },
    "TABS": [],
}
