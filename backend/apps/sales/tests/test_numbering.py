"""Invoice numbering is minted at CHARGE only — held/voided orders never
consume a number, so completed-invoice numbers stay gapless per terminal/year.

Regression for the reported "day closed at 0032, reopened at 0036" gaps, which
came from held/voided orders burning invoice numbers.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import transaction

from apps.sales.models import Invoice
from apps.sales.services.numbering import next_invoice_number
from apps.tenants.models import Branch, Tenant, Terminal

pytestmark = pytest.mark.django_db

YEAR = dt.date.today().year


@pytest.fixture
def scene(db):
    tenant = Tenant.objects.create(
        business_name="R", ntn=f"N{uuid.uuid4().hex[:8]}",
        business_type="sole_proprietor", province="PUNJAB", fbr_connection_type="none",
    )
    branch = Branch.objects.create(tenant=tenant, name="Main", code="KK", address="x")
    term = Terminal.objects.create(
        tenant=tenant, branch=branch, name="Terminal 3", terminal_index=3,
        device_fingerprint=uuid.uuid4().hex,
    )
    from django.contrib.auth import get_user_model
    from apps.tenants.models import TenantMembership
    user = get_user_model().objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test", password="x", full_name="C",
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role="cashier")
    return tenant, branch, term, user


def _inv(tenant, branch, term, user, number, *, is_held):
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=term, cashier=user,
        local_invoice_number=number, invoice_date=dt.date.today(),
        status="pending_sync", is_held=is_held, grand_total=Decimal("100"),
        client_uuid=uuid.uuid4(),
    )


def _next(term):
    with transaction.atomic():
        return next_invoice_number(terminal=term)


def test_first_completed_invoice_is_0001(scene):
    tenant, branch, term, user = scene
    assert _next(term) == f"KK-T3-{YEAR}-0000001"


def test_held_orders_do_not_advance_the_sequence(scene):
    tenant, branch, term, user = scene
    # Several held/open orders exist with high tags — they must NOT count.
    _inv(tenant, branch, term, user, f"KK-T3-{YEAR}-0000032", is_held=True)
    _inv(tenant, branch, term, user, f"KK-T3-{YEAR}-0000035", is_held=True)
    # Next COMPLETED invoice is still 0001 (no completed invoice yet).
    assert _next(term) == f"KK-T3-{YEAR}-0000001"


def test_sequence_is_gapless_across_completed_invoices(scene):
    tenant, branch, term, user = scene
    n1 = _next(term)
    _inv(tenant, branch, term, user, n1, is_held=False)  # charged
    # A held order in between (voided later) must not create a gap.
    _inv(tenant, branch, term, user, f"KK-T3-{YEAR}-9999999", is_held=True)
    n2 = _next(term)
    assert n1 == f"KK-T3-{YEAR}-0000001"
    assert n2 == f"KK-T3-{YEAR}-0000002"  # gapless — the held row is ignored


def test_completed_invoices_advance_normally(scene):
    tenant, branch, term, user = scene
    for expected in range(1, 4):
        n = _next(term)
        assert n == f"KK-T3-{YEAR}-{expected:07d}"
        _inv(tenant, branch, term, user, n, is_held=False)
