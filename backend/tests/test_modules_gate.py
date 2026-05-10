"""Per-tenant module gate (super-admin-controlled feature catalog).

Foundation tests for the module system:
  - catalog ordering + forced flags are stable
  - HasModule allows enabled, blocks disabled, ignores config for forced
  - default_modules_enabled returns the full catalog (no surprise lockouts
    after migration)
  - normalise rejects unknown keys, always includes forced ones
  - GET /api/me/modules/ returns the catalog + the tenant's enabled set

The endpoint annotations themselves (which views require which module)
land in a follow-up commit and have their own tests there.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.permissions import HasModule
from apps.tenants.modules import (
    FORCED_MODULE_KEYS,
    MODULE_KEYS,
    MODULES,
    default_modules_enabled,
    is_module_enabled,
    normalise,
)


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post(
        "/api/auth/login/",
        {"email": email, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_has_unique_keys():
    keys = [m["key"] for m in MODULES]
    assert len(keys) == len(set(keys)), "Module keys must be unique."


def test_catalog_includes_required_modules():
    """Sanity check — the keys the endpoint annotations will reference
    must exist in the catalog. This guards against typo-driven gates."""
    expected = {
        "sales", "fbr", "customers", "branches", "terminals", "inventory",
        "returns", "debit_credit_notes", "manual_amendments",
        "payments_advanced", "customer_display", "hardware",
        "reports_basic", "reports_advanced", "audit_log",
    }
    assert set(MODULE_KEYS) == expected


def test_forced_modules_are_sales_and_fbr():
    """If you change this list, audit every place that calls
    is_module_enabled — disabling sales/fbr would brick the product."""
    assert FORCED_MODULE_KEYS == {"sales", "fbr"}


def test_default_modules_enabled_is_everything():
    """The migration backfill assumes this; if you change it, update
    apps/tenants/migrations/0007_tenant_modules_enabled.py too."""
    assert default_modules_enabled() == list(MODULE_KEYS)


# ---------------------------------------------------------------------------
# normalise()
# ---------------------------------------------------------------------------


def test_normalise_rejects_unknown_keys():
    out = normalise(["sales", "branches", "evil_module"])
    assert "evil_module" not in out


def test_normalise_always_includes_forced():
    """Even if the operator submits a checklist that omits forced modules,
    we re-add them so the JSON in the DB is internally consistent."""
    out = normalise([])
    assert "sales" in out
    assert "fbr" in out


def test_normalise_preserves_catalog_order():
    """Deterministic ordering means JSON diffs in the audit log read
    naturally and admin pages always render the same order."""
    out = normalise(["audit_log", "sales", "branches"])
    # Catalog order: sales (1), fbr (2 forced auto-add), branches (4),
    # audit_log (15). Forced ones are auto-included.
    assert out.index("sales") < out.index("fbr")
    assert out.index("fbr") < out.index("branches")
    assert out.index("branches") < out.index("audit_log")


# ---------------------------------------------------------------------------
# is_module_enabled() helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_is_module_enabled_honours_forced(tenant):
    """Even if modules_enabled is empty, sales + fbr always return True."""
    tenant.modules_enabled = []
    tenant.save()
    assert is_module_enabled(tenant, "sales") is True
    assert is_module_enabled(tenant, "fbr") is True
    assert is_module_enabled(tenant, "branches") is False


@pytest.mark.django_db
def test_is_module_enabled_returns_false_for_unknown(tenant):
    tenant.modules_enabled = list(MODULE_KEYS)
    tenant.save()
    assert is_module_enabled(tenant, "module_that_does_not_exist") is False


# ---------------------------------------------------------------------------
# HasModule DRF class — tested via a synthetic view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_has_module_blocks_disabled(rf, tenant, owner_user):
    from rest_framework.request import Request
    from apps.tenants.middleware import TenantContextMiddleware  # noqa: F401

    tenant.modules_enabled = ["sales", "fbr"]  # branches off
    tenant.save()

    perm = HasModule.for_module("branches")()
    request = rf.get("/api/branches/")
    request.user = owner_user
    request.tenant_id = tenant.id
    request.tenant_membership = type(
        "Stub", (), {"role": "owner"},
    )()
    drf_req = Request(request)
    drf_req.user = owner_user
    drf_req.tenant_id = tenant.id
    drf_req.tenant_membership = request.tenant_membership

    assert perm.has_permission(drf_req, view=None) is False


@pytest.mark.django_db
def test_has_module_allows_enabled(rf, tenant, owner_user):
    from rest_framework.request import Request

    tenant.modules_enabled = ["sales", "fbr", "branches"]
    tenant.save()

    perm = HasModule.for_module("branches")()
    request = rf.get("/api/branches/")
    request.user = owner_user
    request.tenant_id = tenant.id
    drf_req = Request(request)
    drf_req.user = owner_user
    drf_req.tenant_id = tenant.id

    assert perm.has_permission(drf_req, view=None) is True


@pytest.mark.django_db
def test_has_module_allows_forced_even_when_omitted(rf, tenant, owner_user):
    """Forced modules are enabled regardless of the JSON list — the
    UI checkbox for these is locked, but defense-in-depth on the server
    means the gate also ignores the config."""
    from rest_framework.request import Request

    tenant.modules_enabled = []  # empty config!
    tenant.save()

    perm = HasModule.for_module("sales")()
    request = rf.get("/api/sales/invoices/")
    request.user = owner_user
    request.tenant_id = tenant.id
    drf_req = Request(request)
    drf_req.user = owner_user
    drf_req.tenant_id = tenant.id

    assert perm.has_permission(drf_req, view=None) is True


# ---------------------------------------------------------------------------
# GET /api/me/modules/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_modules_endpoint_returns_catalog_and_enabled(tenant, owner_user):
    api = APIClient()
    _login(api, owner_user.email)

    # Disable a couple of optional modules.
    tenant.modules_enabled = ["sales", "fbr", "customers", "reports_basic"]
    tenant.save()

    resp = api.get("/api/me/modules/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["catalog"], list)
    assert len(body["catalog"]) == len(MODULE_KEYS)
    # The catalog rows include the schema fields the UI needs.
    assert {"key", "label", "group", "description", "forced"} <= set(
        body["catalog"][0].keys(),
    )
    # Enabled set: the four explicitly listed PLUS forced ones (sales, fbr).
    enabled = set(body["enabled"])
    assert enabled == {"sales", "fbr", "customers", "reports_basic"}
    # Disabled is everything else.
    assert "branches" not in enabled
    assert "inventory" not in enabled


@pytest.mark.django_db
def test_modules_endpoint_requires_tenant_context(owner_user):
    """A user with no tenant context (e.g., a stale JWT after membership
    revocation) gets 403, not a 500."""
    api = APIClient()
    _login(api, owner_user.email)
    # Logged in is fine; remove the membership to simulate the edge case.
    from apps.tenants.models import TenantMembership
    TenantMembership.objects.filter(user=owner_user).update(is_active=False)

    resp = api.get("/api/me/modules/")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Integration — gates actually block real endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_branches_endpoint_returns_403_when_module_disabled(
    tenant, owner_user,
):
    """When super-admin has disabled the 'branches' module for this
    tenant, the Branches API should return 403 even for the owner role.
    This is what enables the 'seller without branches' configuration."""
    api = APIClient()
    _login(api, owner_user.email)

    # Disable branches.
    tenant.modules_enabled = ["sales", "fbr", "customers"]
    tenant.save()

    resp = api.get("/api/branches/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_branches_endpoint_works_when_module_enabled(
    tenant, owner_user,
):
    """Sanity: with the module on, the same call succeeds."""
    api = APIClient()
    _login(api, owner_user.email)
    # Default: all modules enabled (set by callable default at create time).
    resp = api.get("/api/branches/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_inventory_endpoint_returns_403_when_module_disabled(
    tenant, owner_user,
):
    api = APIClient()
    _login(api, owner_user.email)
    tenant.modules_enabled = ["sales", "fbr"]
    tenant.save()
    resp = api.get("/api/inventory/stock-levels/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_sales_invoices_remain_accessible_even_with_minimal_modules(
    tenant, owner_user,
):
    """Sales/FBR are forced — even if the operator turns off everything
    else, invoices still work. This is the safety net for the platform."""
    api = APIClient()
    _login(api, owner_user.email)
    tenant.modules_enabled = []  # nothing — but sales/fbr are forced
    tenant.save()
    resp = api.get("/api/sales/invoices/")
    assert resp.status_code == 200
