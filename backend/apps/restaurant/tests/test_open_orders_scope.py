"""Open orders must be scoped to the terminal that owns them.

Regression: open_orders_qs filtered only by tenant/branch, so Terminal 2's
unpaid orders showed up on Terminal 3. Each till owns its own open orders;
only the Admin invoice list is cross-terminal.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.restaurant.services import open_orders_qs
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
    branch = Branch.objects.create(tenant=tenant, name="Main", code="M", address="x")
    t2 = Terminal.objects.create(tenant=tenant, branch=branch, name="T2",
                                 device_fingerprint=uuid.uuid4().hex)
    t3 = Terminal.objects.create(tenant=tenant, branch=branch, name="T3",
                                 device_fingerprint=uuid.uuid4().hex)
    user = get_user_model().objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test", password="x", full_name="C",
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role="cashier")
    return tenant, branch, t2, t3, user


def _open_order(tenant, branch, terminal, num, cashier):
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=cashier,
        local_invoice_number=num, invoice_date=dt.date.today(),
        status="pending_sync", is_held=True, order_status="open",
        order_type="dine_in", grand_total=Decimal("100"),
        client_uuid=uuid.uuid4(),
    )


def test_terminal_sees_only_its_own_open_orders(scene):
    tenant, branch, t2, t3, cashier = scene
    _open_order(tenant, branch, t2, "T2-1", cashier)
    _open_order(tenant, branch, t3, "T3-1", cashier)

    t2_orders = list(open_orders_qs(tenant.id, terminal_id=str(t2.id)))
    t3_orders = list(open_orders_qs(tenant.id, terminal_id=str(t3.id)))

    assert {o.local_invoice_number for o in t2_orders} == {"T2-1"}
    assert {o.local_invoice_number for o in t3_orders} == {"T3-1"}


def test_branch_scope_still_sees_all_terminals(scene):
    # Admin/KDS (no terminal filter) must still see the whole branch.
    tenant, branch, t2, t3, cashier = scene
    _open_order(tenant, branch, t2, "T2-1", cashier)
    _open_order(tenant, branch, t3, "T3-1", cashier)

    all_orders = list(open_orders_qs(tenant.id, branch_id=str(branch.id)))
    assert {o.local_invoice_number for o in all_orders} == {"T2-1", "T3-1"}


def test_terminal_scope_excludes_other_terminal_even_same_branch(scene):
    tenant, branch, t2, t3, cashier = scene
    _open_order(tenant, branch, t2, "T2-1", cashier)
    t3_orders = list(open_orders_qs(tenant.id, branch_id=str(branch.id), terminal_id=str(t3.id)))
    assert t3_orders == []


def test_resume_rejects_other_terminals_order(scene):
    """A till may not resume an order another terminal owns (occupied-but-not-
    openable). getOpenOrder(?id=&terminal=) 404s for a foreign terminal."""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.restaurant.views import OpenOrderView

    tenant, branch, t2, t3, cashier = scene
    order = _open_order(tenant, branch, t2, "T2-1", cashier)  # owned by T2
    factory = APIRequestFactory()

    def _fetch(as_terminal):
        req = factory.get(f"/api/restaurant/orders/?id={order.id}&terminal={as_terminal.id}")
        force_authenticate(req, user=cashier)
        req.tenant_id = str(tenant.id)
        return OpenOrderView.as_view()(req)

    # T2 (owner) can resume; T3 cannot.
    assert _fetch(t2).status_code == 200
    assert _fetch(t3).status_code == 404
