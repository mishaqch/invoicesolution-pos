"""Non-fiscal tenants (fbr_connection_type='none') — e.g. the TDCP resort.

Their invoices must be created, synced and reported like normal but NEVER
submitted to FBR. The submit task must short-circuit and the invoice must keep
fbr_invoice_number=NULL so receipts omit the FBR block.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.fbr.tasks import submit_invoice_to_fbr
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal, Tenant

User = get_user_model()

pytestmark = pytest.mark.django_db


def _make_invoice(fbr_connection_type: str) -> Invoice:
    tenant = Tenant.objects.create(
        business_name="TDCP Kallar Kahar",
        ntn=str(uuid.uuid4().int)[:7],
        business_type="sole_proprietor",
        business_mode="pos",
        vertical="restaurant",
        fbr_connection_type=fbr_connection_type,
    )
    branch = Branch.objects.create(tenant=tenant, name="Kallar Kahar", code="KK")
    terminal = Terminal.objects.create(tenant=tenant, branch=branch, name="T1")
    cashier = User.objects.create(
        email=f"cashier-{uuid.uuid4().hex[:8]}@tdcp.test", full_name="Test Cashier",
    )
    return Invoice.objects.create(
        tenant=tenant,
        branch=branch,
        terminal=terminal,
        cashier=cashier,
        local_invoice_number="KK-T1-2026-0000001",
        client_uuid=uuid.uuid4(),
        invoice_date=dt.date.today(),
        status="pending_sync",
        subtotal=Decimal("1000"),
        tax_total=Decimal("160"),
        grand_total=Decimal("1160"),
        paid_total=Decimal("1160"),
    )


def test_non_fiscal_invoice_is_not_submitted():
    invoice = _make_invoice("none")
    result = submit_invoice_to_fbr(str(invoice.id))
    assert result == {"skipped": "non_fiscal", "status": "pending_sync"}
    invoice.refresh_from_db()
    # Never fiscalised — no FBR number, status unchanged.
    assert invoice.fbr_invoice_number is None
    assert invoice.status == "pending_sync"


def test_fiscal_tenant_without_token_still_defers_not_skips():
    # A normal di_api tenant with no token must DEFER (not "non_fiscal"),
    # proving the new branch only triggers for fbr_connection_type='none'.
    invoice = _make_invoice("di_api")
    result = submit_invoice_to_fbr(str(invoice.id))
    assert result.get("skipped") != "non_fiscal"
