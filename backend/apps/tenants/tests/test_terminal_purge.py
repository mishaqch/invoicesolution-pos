"""Purging a terminal must be possible ONLY when it never traded.

DELETE /terminals/<id>/ deactivates rather than deletes, because invoices,
cash sessions, returns and sync logs all reference the terminal with
on_delete=PROTECT and that history is legally retained for six years. The
side effect was that a terminal created by mistake — never paired, never
used — could never be removed from the list (TDCP's "Terminal Dinning" T4).

purge/ fills that gap without weakening the protection: deactivated first,
and provably no history.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.sales.models import Invoice
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal

pytestmark = pytest.mark.django_db


@pytest.fixture
def scene(db):
    tenant = Tenant.objects.create(
        business_name="Resort", ntn=f"N{uuid.uuid4().hex[:8]}",
        business_type="sole_proprietor", province="PUNJAB",
        fbr_connection_type="none",
    )
    branch = Branch.objects.create(tenant=tenant, name="Main", code="KK", address="x")
    owner = get_user_model().objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test", password="x", full_name="Owner",
    )
    TenantMembership.objects.create(tenant=tenant, user=owner, role="owner")
    api = APIClient()
    api.force_authenticate(owner)
    return tenant, branch, owner, api


def _terminal(tenant, branch, *, name, active=True):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name=name,
        device_fingerprint=f"unpaired-{uuid.uuid4().hex}", is_active=active,
    )


def test_purge_removes_a_never_used_terminal(scene):
    """The whole point: a mistake row can finally be cleared."""
    tenant, branch, _, api = scene
    t = _terminal(tenant, branch, name="Terminal Dinning", active=False)

    resp = api.delete(f"/api/terminals/{t.id}/purge/")

    assert resp.status_code == 204, resp.data
    assert not Terminal.objects.filter(pk=t.id).exists()


def test_purge_refuses_an_active_terminal(scene):
    """Two-step by design: deactivate, THEN delete. Never one mis-click."""
    tenant, branch, _, api = scene
    t = _terminal(tenant, branch, name="Live Till", active=True)

    resp = api.delete(f"/api/terminals/{t.id}/purge/")

    assert resp.status_code == 400
    assert Terminal.objects.filter(pk=t.id).exists()


def test_purge_refuses_a_terminal_with_invoices(scene):
    """The guard that matters: history must never be destroyed."""
    tenant, branch, owner, api = scene
    t = _terminal(tenant, branch, name="Used Till", active=False)
    Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=t, cashier=owner,
        client_uuid=uuid.uuid4(), local_invoice_number="KK-T9-2026-0000001",
        invoice_date="2026-10-08", status="pending_sync",
        subtotal=Decimal("100"), discount_total=Decimal("0"),
        tax_total=Decimal("0"), grand_total=Decimal("100"),
        paid_total=Decimal("100"), change_given=Decimal("0"),
    )

    resp = api.delete(f"/api/terminals/{t.id}/purge/")

    assert resp.status_code == 400
    assert "1 invoices" in str(resp.data), resp.data
    assert Terminal.objects.filter(pk=t.id).exists()


def test_purge_is_tenant_scoped(scene):
    """Another tenant's terminal must be invisible, not merely refused."""
    _, _, _, api = scene
    other_tenant = Tenant.objects.create(
        business_name="Other", ntn=f"N{uuid.uuid4().hex[:8]}",
        business_type="sole_proprietor", province="PUNJAB",
        fbr_connection_type="none",
    )
    other_branch = Branch.objects.create(
        tenant=other_tenant, name="B", code="OT", address="x",
    )
    victim = _terminal(other_tenant, other_branch, name="Not Yours", active=False)

    resp = api.delete(f"/api/terminals/{victim.id}/purge/")

    assert resp.status_code == 404
    assert Terminal.objects.filter(pk=victim.id).exists()
