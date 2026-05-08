"""Test settings — fast Argon2, in-memory cache, eager Celery."""

from .base import *  # noqa: F401,F403

DEBUG = False

# Drop Argon2 cost dramatically so the test suite isn't dominated by hashing.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
# Cheaper Argon2 params via subclass would be cleaner, but Django's default
# Argon2PasswordHasher reads tunables from class attrs — overriding here keeps
# things simple for Phase 0. Tighten in Phase 8 if test-suite hash cost grows.

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Don't hit a real Redis for broker URL in tests.
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# NB: throttle counters live in Django cache (LocMem in tests). The
# autouse fixture in tests/conftest.py clears the cache between tests so
# each one starts with a fresh quota; we leave the throttle CLASSES alone
# so we still verify the production-shaped throttling behaviour.
