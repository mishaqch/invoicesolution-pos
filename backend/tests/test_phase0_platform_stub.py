"""Phase 0 platform stub.

Tests cover:
- Three default subscription plans seeded with stable codes.
- PlatformSettings singleton exists and refuses a second row.
- JWT carries is_platform_staff + platform_role claims.
- Platform-staff users are blocked from tenant API endpoints.
- Non-platform users are blocked from /api/platform/* endpoints.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.platform_admin.models import (
    PlatformSettings,
    Subscription,
    SubscriptionPlan,
)


# ---------------------------------------------------------------------------
# Seed integrity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_three_default_plans_exist():
    codes = set(SubscriptionPlan.objects.values_list("code", flat=True))
    assert {"starter", "pro", "enterprise"}.issubset(codes)


@pytest.mark.django_db
def test_starter_plan_has_expected_limits():
    starter = SubscriptionPlan.objects.get(code="starter")
    assert starter.max_branches == 1
    assert starter.max_terminals == 2
    assert starter.monthly_price_paisa == 200_000  # Rs 2,000


@pytest.mark.django_db
def test_enterprise_plan_has_unlimited_resources():
    ent = SubscriptionPlan.objects.get(code="enterprise")
    assert ent.max_branches is None
    assert ent.max_terminals is None
    assert ent.max_products is None
    assert ent.max_users is None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_platform_settings_singleton_exists():
    """The seed migration creates the singleton row."""
    assert PlatformSettings.objects.count() == 1
    s = PlatformSettings.objects.first()
    assert s.platform_name == "Pakistan POS"
    assert s.default_trial_days == 14


@pytest.mark.django_db
def test_platform_settings_load_helper():
    """`load()` is idempotent — returns existing or creates."""
    PlatformSettings.objects.all().delete()
    a = PlatformSettings.load()
    b = PlatformSettings.load()
    assert a.pk == b.pk
    assert PlatformSettings.objects.count() == 1


# ---------------------------------------------------------------------------
# Subscription model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_subscription_links_tenant_to_plan(tenant):
    plan = SubscriptionPlan.objects.get(code="starter")
    sub = Subscription.objects.create(
        tenant=tenant, plan=plan, status="trial", billing_cycle="monthly",
    )
    assert sub.tenant == tenant
    assert sub.plan == plan
    assert sub.status == "trial"


# ---------------------------------------------------------------------------
# JWT claims
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_login_jwt_carries_platform_staff_claims_when_set(tenant, owner_user):
    """A platform-staff user's JWT must include the new claims."""
    owner_user.is_platform_staff = True
    owner_user.platform_role = "support_agent"
    owner_user.save(update_fields=["is_platform_staff", "platform_role"])

    api = APIClient()
    resp = api.post(
        "/api/auth/login/",
        {"email": owner_user.email, "password": "testpass1234"},
        format="json",
    )
    assert resp.status_code == 200, resp.content

    # Decode the access token claims.
    import jwt
    from django.conf import settings
    payload = jwt.decode(
        resp.json()["access"],
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
    )
    assert payload["is_platform_staff"] is True
    assert payload["platform_role"] == "support_agent"


@pytest.mark.django_db
def test_login_jwt_default_platform_claims_for_tenant_user(tenant, owner_user):
    """A regular tenant user's JWT must have is_platform_staff=False."""
    api = APIClient()
    resp = api.post(
        "/api/auth/login/",
        {"email": owner_user.email, "password": "testpass1234"},
        format="json",
    )
    import jwt
    from django.conf import settings
    payload = jwt.decode(
        resp.json()["access"],
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
    )
    assert payload["is_platform_staff"] is False
    assert payload["platform_role"] == ""


# ---------------------------------------------------------------------------
# Tenant-API gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_platform_staff_blocked_from_tenant_api(tenant, owner_user):
    """A platform-staff user (without impersonation context) cannot reach
    tenant-side /api/ endpoints. Phase 9 adds the impersonation flow."""
    owner_user.is_platform_staff = True
    owner_user.platform_role = "support_agent"
    owner_user.save(update_fields=["is_platform_staff", "platform_role"])

    api = APIClient()
    login = api.post(
        "/api/auth/login/",
        {"email": owner_user.email, "password": "testpass1234"},
        format="json",
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")

    # Try a tenant-side endpoint — should be 403 Forbidden.
    resp = api.get("/api/branches/")
    assert resp.status_code == 403
    assert "platform staff" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_non_platform_user_blocked_from_platform_api(tenant, owner_user):
    """Conversely, a tenant user cannot reach /api/platform/* even though
    no such routes exist yet — the gate fires before routing."""
    api = APIClient()
    login = api.post(
        "/api/auth/login/",
        {"email": owner_user.email, "password": "testpass1234"},
        format="json",
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")

    resp = api.get("/api/platform/whatever/")
    assert resp.status_code == 403
    assert "platform staff only" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_regular_user_can_still_reach_tenant_api(tenant, owner_user):
    """Sanity check: the gate doesn't break the normal path."""
    api = APIClient()
    login = api.post(
        "/api/auth/login/",
        {"email": owner_user.email, "password": "testpass1234"},
        format="json",
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")

    resp = api.get("/api/branches/")
    # 200 (empty list) — not 403.
    assert resp.status_code == 200
