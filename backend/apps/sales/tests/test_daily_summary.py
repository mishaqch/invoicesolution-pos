"""End-of-day daily summary (Z-report) aggregation.

Covers the figures the manager asked to see on Day-close / logout:
Total Sales, Total Orders, Cancelled Items/Orders, payment breakup
(cash/card/online), and Total Discount. Money is Decimal throughout.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from apps.sales.models import Invoice, Payment, SaleItem
from apps.sales.services.sessions import daily_summary, session_summary
from apps.tenants.models import Branch, CashSession, Tenant, Terminal

pytestmark = pytest.mark.django_db

TODAY = dt.date.today()


@pytest.fixture
def scene(db):
    tenant = Tenant.objects.create(
        business_name="Resort", ntn=f"N{uuid.uuid4().hex[:8]}",
        business_type="sole_proprietor", province="PUNJAB",
        fbr_connection_type="none",
    )
    branch = Branch.objects.create(tenant=tenant, name="Main", code="KK", address="x")
    term = Terminal.objects.create(
        tenant=tenant, branch=branch, name="Terminal 1", terminal_index=1,
        device_fingerprint=uuid.uuid4().hex,
    )
    from django.contrib.auth import get_user_model
    from apps.tenants.models import TenantMembership
    user = get_user_model().objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@t.test", password="x", full_name="C",
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role="cashier")
    return tenant, branch, term, user


def _inv(scene, number, *, status="pending_sync", is_held=False,
         grand="1000", discount="0", tax="0", session=None):
    tenant, branch, term, user = scene
    return Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=term, cashier=user,
        cash_session=session,
        local_invoice_number=number, invoice_date=TODAY,
        status=status, is_held=is_held,
        grand_total=Decimal(grand), discount_total=Decimal(discount),
        tax_total=Decimal(tax), client_uuid=uuid.uuid4(),
    )


def _pay(invoice, method, amount, status="completed"):
    return Payment.objects.create(
        tenant_id=invoice.tenant_id, invoice=invoice,
        payment_method=method, amount=Decimal(amount), status=status,
    )


def test_daily_summary_counts_completed_sales_only(scene):
    tenant, branch, term, user = scene
    _inv(scene, "KK-T1-1", grand="1000", tax="160", discount="50")
    _inv(scene, "KK-T1-2", grand="2000", tax="320", discount="0")
    # Held must NOT count.
    _inv(scene, "KK-T1-3", grand="9999", is_held=True)

    s = daily_summary(tenant_id=tenant.id, date=TODAY)
    assert s["total_orders"] == 2
    assert Decimal(s["total_sales"]) == Decimal("3000")
    assert Decimal(s["total_discount"]) == Decimal("50")
    assert Decimal(s["total_tax"]) == Decimal("480")


def test_daily_summary_payment_breakup(scene):
    tenant, branch, term, user = scene
    i1 = _inv(scene, "KK-T1-1", grand="1000")
    i2 = _inv(scene, "KK-T1-2", grand="2000")
    _pay(i1, "cash", "1000")
    _pay(i2, "card", "1500")
    _pay(i2, "online", "500")

    s = daily_summary(tenant_id=tenant.id, date=TODAY)
    bk = s["payment_breakup"]
    assert Decimal(bk["cash"]["total"]) == Decimal("1000")
    assert bk["cash"]["count"] == 1
    assert Decimal(bk["card"]["total"]) == Decimal("1500")
    assert Decimal(bk["online"]["total"]) == Decimal("500")


def test_daily_summary_cancelled_orders_and_items(scene):
    tenant, branch, term, user = scene
    from apps.catalog.models import Product, UnitOfMeasure
    uom = (UnitOfMeasure.objects.filter(code="NO").first()
           or UnitOfMeasure.objects.create(code="NO", name_en="Number"))
    prod = Product.objects.create(
        tenant=tenant, name="Tea", sku="TEA-1", uom=uom, sale_price=Decimal("100"),
    )
    sold = _inv(scene, "KK-T1-1", grand="1000")
    _inv(scene, "KK-T1-2", grand="0", status="cancelled")
    SaleItem.objects.create(
        invoice=sold, line_number=1, product=prod,
        product_name="Tea", product_sku="TEA-1", uom_code="NO",
        quantity=Decimal("1"), unit_price=Decimal("100"),
        tax_rate=Decimal("0"), tax_amount=Decimal("0"), line_total=Decimal("100"),
        is_cancelled=True,
    )
    s = daily_summary(tenant_id=tenant.id, date=TODAY)
    assert s["cancelled_orders"] == 1
    assert s["cancelled_items"] == 1
    assert Decimal(s["total_sales"]) == Decimal("1000")


def test_daily_summary_scoped_by_other_day_is_empty(scene):
    tenant, branch, term, user = scene
    _inv(scene, "KK-T1-1", grand="1000")
    s = daily_summary(tenant_id=tenant.id, date=TODAY - dt.timedelta(days=1))
    assert s["total_orders"] == 0
    assert Decimal(s["total_sales"]) == Decimal("0")


def test_session_summary_merges_cash_context(scene):
    tenant, branch, term, user = scene
    from django.utils import timezone
    sess = CashSession.objects.create(
        tenant=tenant, branch=branch, terminal=term, cashier=user,
        opened_at=timezone.now(), opened_with_amount=Decimal("500"),
    )
    _inv(scene, "KK-T1-1", grand="1000", session=sess)
    s = session_summary(sess)
    assert s["session_id"] == str(sess.id)
    assert Decimal(s["opening_cash"]) == Decimal("500")
    assert s["total_orders"] == 1
    assert Decimal(s["total_sales"]) == Decimal("1000")
