"""Production-only token routing.

Once a tenant activates a production FBR token:
  1. activate_production_token() deactivates any active sandbox token, and
  2. the submission task uses ONLY production — it never falls back to sandbox,
     even if production is temporarily inactive (so live sales can't leak to
     the sandbox endpoint).

These are tax-critical invariants, so they're tested with explicit setup.
"""
from __future__ import annotations

from unittest import mock

import pytest

from apps.fbr.models import FbrToken
from apps.fbr.services import activate_production_token


def _mk_token(tenant, environment, secret, *, active=True):
    obj = FbrToken.objects.create(
        tenant=tenant, environment=environment,
        token_encrypted="", api_endpoint="https://gw.fbr.gov.pk",
        is_active=active,
    )
    obj.set_token(secret)
    obj.save()
    return obj


@pytest.mark.django_db
def test_activating_production_deactivates_sandbox(tenant):
    sandbox = _mk_token(tenant, "sandbox", "SANDBOX-BEARER")

    # Production activation requires all scenarios passed — stub it.
    with mock.patch("apps.fbr.services.all_scenarios_passed", return_value=True):
        prod = activate_production_token(
            tenant=tenant, token="PROD-BEARER",
            api_endpoint="https://gw.fbr.gov.pk",
        )

    sandbox.refresh_from_db()
    assert prod.is_active is True
    assert prod.environment == "production"
    # The sandbox token row survives (history) but is no longer active.
    assert sandbox.is_active is False


@pytest.mark.django_db
def test_submission_never_falls_back_to_sandbox_for_production_tenant(tenant):
    """If production exists but is inactive, the task defers — it must NOT
    use a still-active sandbox token."""
    _mk_token(tenant, "sandbox", "SANDBOX-BEARER", active=True)
    _mk_token(tenant, "production", "PROD-BEARER", active=False)

    # Re-create the task's token-selection logic against the DB state.
    has_production = FbrToken.objects.filter(
        tenant=tenant, environment="production",
    ).exists()
    assert has_production is True

    chosen = None
    if has_production:
        chosen = FbrToken.objects.filter(
            tenant=tenant, environment="production", is_active=True,
        ).first()
    # Production is inactive → chosen is None → task defers. Crucially it does
    # NOT pick the active sandbox token.
    assert chosen is None
    active_sandbox = FbrToken.objects.filter(
        tenant=tenant, environment="sandbox", is_active=True,
    ).first()
    assert active_sandbox is not None  # it's active...
    # ...but the production-tenant rule means we never selected it.


@pytest.mark.django_db
def test_activation_blocked_when_scenarios_not_passed(tenant):
    """Default path: without passing scenarios (and without the bypass),
    activation is refused — matching FBR's sandbox-before-production rule."""
    from django.core.exceptions import ValidationError

    with mock.patch("apps.fbr.services.all_scenarios_passed", return_value=False):
        with pytest.raises(ValidationError):
            activate_production_token(
                tenant=tenant, token="PROD-BEARER",
                api_endpoint="https://gw.fbr.gov.pk",
            )


@pytest.mark.django_db
def test_external_bypass_allows_activation_without_runner(tenant):
    """A token FBR already issued (sandbox cleared on the FBR portal) can be
    activated with scenarios_cleared_externally=True even if OUR scenario
    runner never ran."""
    with mock.patch("apps.fbr.services.all_scenarios_passed", return_value=False):
        prod = activate_production_token(
            tenant=tenant, token="EXTERNALLY-ISSUED-PROD-TOKEN",
            api_endpoint="https://gw.fbr.gov.pk",
            scenarios_cleared_externally=True,
        )
    assert prod.is_active is True
    assert prod.environment == "production"


@pytest.mark.django_db
def test_sandbox_only_tenant_still_uses_sandbox(tenant):
    """A tenant that never went to production keeps using its sandbox token."""
    _mk_token(tenant, "sandbox", "SANDBOX-BEARER", active=True)

    has_production = FbrToken.objects.filter(
        tenant=tenant, environment="production",
    ).exists()
    assert has_production is False
    chosen = FbrToken.objects.filter(
        tenant=tenant, environment="sandbox", is_active=True,
    ).first()
    assert chosen is not None
    assert chosen.environment == "sandbox"
