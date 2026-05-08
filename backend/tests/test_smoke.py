"""Phase-0 smoke tests: identity + tenancy + JWT + PIN login."""

from __future__ import annotations

import pytest
from django.test import Client
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_user_email_lowercased(owner_user):
    assert owner_user.email == "owner@example.com"


@pytest.mark.django_db
def test_pin_hashed_not_stored_plain(cashier_user):
    assert cashier_user.pin_hash != "1234"
    assert cashier_user.check_pin("1234")
    assert not cashier_user.check_pin("9999")


@pytest.mark.django_db
def test_pin_validation_rejects_short_or_alpha(cashier_user):
    with pytest.raises(ValueError):
        cashier_user.set_pin("12")
    with pytest.raises(ValueError):
        cashier_user.set_pin("abcd")


@pytest.mark.django_db
def test_argon2_is_default_password_hasher():
    """Argon2id must be the default — schema requirement, not just available."""
    from django.conf import settings
    assert settings.PASSWORD_HASHERS[0] == \
        "django.contrib.auth.hashers.Argon2PasswordHasher"


# ---------------------------------------------------------------------------
# JWT auth
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_returns_access_refresh_tenant_role(owner_user, tenant):
    api = APIClient()
    resp = api.post(
        "/api/auth/login/",
        {"email": "owner@example.com", "password": "testpass1234"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "access" in body and "refresh" in body
    assert body["user"]["email"] == "owner@example.com"
    assert body["tenant"]["id"] == str(tenant.id)
    assert body["role"] == "owner"


@pytest.mark.django_db
def test_login_token_carries_tenant_id_claim(owner_user):
    """The custom serializer must embed tenant_id + role into the access token."""
    import jwt
    from django.conf import settings

    api = APIClient()
    resp = api.post(
        "/api/auth/login/",
        {"email": "owner@example.com", "password": "testpass1234"},
        format="json",
    )
    access = resp.json()["access"]
    payload = jwt.decode(access, settings.SECRET_KEY, algorithms=["HS256"])
    assert "tenant_id" in payload
    assert payload["role"] == "owner"


@pytest.mark.django_db
def test_pin_login_returns_tokens(cashier_user, tenant):
    api = APIClient()
    resp = api.post(
        "/api/auth/pin-login/",
        {"email": "cashier@example.com", "pin": "1234"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "access" in body
    assert body["role"] == "cashier"
    assert body["tenant"]["id"] == str(tenant.id)


@pytest.mark.django_db
def test_pin_login_wrong_pin_rejected(cashier_user):
    api = APIClient()
    resp = api.post(
        "/api/auth/pin-login/",
        {"email": "cashier@example.com", "pin": "9999"},
        format="json",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tenant middleware
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_me_endpoint_resolves_tenant_from_jwt(owner_user, tenant):
    api = APIClient()
    login = api.post(
        "/api/auth/login/",
        {"email": "owner@example.com", "password": "testpass1234"},
        format="json",
    ).json()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    resp = api.get("/api/auth/me/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant"]["id"] == str(tenant.id)


@pytest.mark.django_db
def test_anonymous_request_to_protected_endpoint_rejected():
    api = APIClient()
    resp = api.get("/api/auth/me/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# System check: tenant-scoped models must use TenantScopedManager
# ---------------------------------------------------------------------------

def test_tenant_scope_check_passes():
    """Phase 0 has no tenant-scoped models yet; check should pass cleanly."""
    from django.core.checks import run_checks
    errors = [e for e in run_checks() if e.id == "tenants.E001"]
    assert errors == []


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_health_endpoint_anonymous():
    """Healthcheck is anonymous; ATOMIC_REQUESTS makes Django open a connection
    even on a no-op view, so we still need the django_db marker to allow that."""
    client = Client()
    resp = client.get("/api/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
