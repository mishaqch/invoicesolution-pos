"""Phase 8 onboarding endpoint — derived flags + state PATCH + tenant scoping."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post(
        "/api/auth/login/",
        {"email": email, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


@pytest.mark.django_db
def test_onboarding_derived_flags_start_false(tenant, owner_user):
    api = APIClient()
    _login(api, owner_user.email)
    resp = api.get("/api/onboarding/")
    assert resp.status_code == 200
    body = resp.json()
    derived = body["derived"]
    assert derived["has_branch"] is False
    assert derived["has_terminal"] is False
    assert derived["has_product"] is False
    assert derived["has_first_sale"] is False
    assert body["state"] == {}


@pytest.mark.django_db
def test_onboarding_state_patch_merges(tenant, owner_user):
    api = APIClient()
    _login(api, owner_user.email)
    api.patch(
        "/api/onboarding/",
        {"profile_done": True},
        format="json",
    )
    api.patch(
        "/api/onboarding/",
        {"branch_done": True},
        format="json",
    )
    resp = api.get("/api/onboarding/")
    state = resp.json()["state"]
    assert state["profile_done"] is True
    assert state["branch_done"] is True


@pytest.mark.django_db
def test_onboarding_derived_branch_flips_after_branch_create(
    tenant, owner_user,
):
    from apps.tenants.models import Branch
    api = APIClient()
    _login(api, owner_user.email)
    Branch.objects.create(
        tenant=tenant, name="HQ", code="HQ",
        address="x", city="x", province="SINDH",
    )
    resp = api.get("/api/onboarding/")
    assert resp.json()["derived"]["has_branch"] is True


@pytest.mark.django_db
def test_onboarding_get_mirrors_derived_into_state_json(
    tenant, owner_user,
):
    """Closes the gap where super-admin saw onboarding_state={} even though
    the tenant had completed real steps. On every GET, derived true should
    flip the matching `*_done` key in the JSON so Django admin sees it."""
    from apps.tenants.models import Branch, Tenant
    api = APIClient()
    _login(api, owner_user.email)
    Branch.objects.create(
        tenant=tenant, name="HQ", code="HQ",
        address="x", city="x", province="SINDH",
    )

    # Before the GET, the JSON is empty.
    tenant.refresh_from_db()
    assert tenant.onboarding_state == {}

    api.get("/api/onboarding/")

    # After the GET, the JSON reflects the live derived flag.
    tenant.refresh_from_db()
    assert tenant.onboarding_state.get("branch_done") is True
    # Other keys not yet derived stay absent.
    assert "terminal_done" not in tenant.onboarding_state


@pytest.mark.django_db
def test_onboarding_mirror_does_not_clobber_operator_overrides(
    tenant, owner_user,
):
    """If an operator has set dismissed_at or a manual key via PATCH, a
    subsequent GET that mirrors derived flags must not erase those keys."""
    api = APIClient()
    _login(api, owner_user.email)

    # Operator dismisses the wizard via PATCH.
    api.patch(
        "/api/onboarding/",
        {"dismissed_at": "2026-05-10T12:00:00Z", "profile_done": True},
        format="json",
    )

    # Now create a branch so a derived flag is true.
    from apps.tenants.models import Branch
    Branch.objects.create(
        tenant=tenant, name="HQ", code="HQ",
        address="x", city="x", province="SINDH",
    )

    api.get("/api/onboarding/")

    tenant.refresh_from_db()
    assert tenant.onboarding_state["dismissed_at"] == "2026-05-10T12:00:00Z"
    assert tenant.onboarding_state["profile_done"] is True
    # And the derived mirror still added branch_done on top.
    assert tenant.onboarding_state["branch_done"] is True


@pytest.mark.django_db
def test_onboarding_mirror_is_idempotent(tenant, owner_user):
    """Calling GET twice in a row must not over-write the JSON the second
    time (no spurious `updated_at` churn) — only changed keys should write."""
    from apps.tenants.models import Tenant, Branch
    api = APIClient()
    _login(api, owner_user.email)
    Branch.objects.create(
        tenant=tenant, name="HQ", code="HQ",
        address="x", city="x", province="SINDH",
    )

    api.get("/api/onboarding/")
    tenant.refresh_from_db()
    first_updated = tenant.updated_at

    # Second GET should NOT re-save (branch_done is already true).
    api.get("/api/onboarding/")
    tenant.refresh_from_db()
    assert tenant.updated_at == first_updated
