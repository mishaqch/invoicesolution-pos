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
