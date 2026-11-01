"""create_invoice resolves the services rate from the tender, server-side.

The terminal already swaps the rate before syncing, so for an up-to-date till
this changes nothing — the server simply arrives at the same answer. It matters
for the paths that DON'T swap: an older .exe still sending 16% on a card sale,
and any future client that forgets.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product, UnitOfMeasure
from apps.sales.services.checkout import create_invoice
from apps.tenants.models import Branch, Tenant, Terminal

pytestmark = pytest.mark.django_db


@pytest.fixture
def scene(db):
    from django.contrib.auth import get_user_model
    tenant = Tenant.objects.create(
        business_name="Resort", ntn=str(uuid.uuid4().int)[:7],
        business_type="sole_proprietor", business_mode="pos",
        vertical="restaurant", fbr_connection_type="none",
        services_tax_rate_standard=Decimal("16.00"),
        services_tax_rate_card=Decimal("8.00"),
    )
    branch = Branch.objects.create(tenant=tenant, name="KK", code="KK")
    terminal = Terminal.objects.create(
        tenant=tenant, branch=branch, name="T1",
        device_fingerprint=uuid.uuid4().hex,
    )
    user = get_user_model().objects.create(
        email=f"c-{uuid.uuid4().hex[:6]}@t.pk", full_name="C",
    )
    uom, _ = UnitOfMeasure.objects.get_or_create(code="PCS", defaults={"name_en": "Pieces"})
    cat = Category.objects.create(tenant=tenant, name="Food", slug="food")
    product = Product.objects.create(
        tenant=tenant, sku="B1", name="Biryani", category=cat, uom=uom,
        sale_price=Decimal("1000"), cost_price=Decimal("0"), is_taxable=True,
    )
    return tenant, branch, terminal, user, product


def _sale(scene, *, payments, tax_rate="16.00"):
    tenant, branch, terminal, user, product = scene
    return create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=user,
        cash_session=None, customer=None,
        cart_lines=[{
            "product": str(product.id), "quantity": "1",
            "unit_price": "1000.00", "tax_rate": tax_rate, "is_taxable": True,
        }],
        payments=payments, client_uuid=uuid.uuid4(),
        local_invoice_number=f"KK-T1-2026-{uuid.uuid4().hex[:6]}",
    )


def _card(amount):
    return {"payment_method": "card_credit", "amount": amount,
            "card_last4": "4242", "card_auth_code": "111222"}


def test_a_card_sale_is_taxed_at_the_reduced_rate(scene):
    inv = _sale(scene, payments=[_card("1080.00")])
    assert inv.tax_total == Decimal("80.0000"), "8% of 1000"
    assert inv.grand_total == Decimal("1080.0000")


def test_an_old_terminal_sending_16_percent_is_corrected(scene):
    """The whole point of moving the rule server-side."""
    inv = _sale(scene, payments=[_card("1080.00")], tax_rate="16.00")
    assert inv.tax_total == Decimal("80.0000")


def test_a_cash_sale_keeps_the_standard_rate(scene):
    inv = _sale(scene, payments=[{"payment_method": "cash", "amount": "1160.00"}])
    assert inv.tax_total == Decimal("160.0000")
    assert inv.grand_total == Decimal("1160.0000")


def test_a_client_sending_8_percent_on_a_cash_sale_is_corrected_upward(scene):
    """Under-charging tax is a liability, so the server fixes this direction too."""
    inv = _sale(
        scene, payments=[{"payment_method": "cash", "amount": "1160.00"}],
        tax_rate="8.00",
    )
    assert inv.tax_total == Decimal("160.0000")


def test_part_cash_part_card_uses_the_standard_rate(scene):
    inv = _sale(scene, payments=[
        _card("1000.00"), {"payment_method": "cash", "amount": "160.00"},
    ])
    assert inv.tax_total == Decimal("160.0000")


def test_a_tenant_without_a_card_rate_is_untouched(scene):
    tenant = scene[0]
    tenant.services_tax_rate_card = None
    tenant.save(update_fields=["services_tax_rate_card"])
    inv = _sale(scene, payments=[_card("1160.00")], tax_rate="16.00")
    assert inv.tax_total == Decimal("160.0000"), "feature off → no swap"


def test_the_invoice_totals_match_its_own_line_items(scene):
    inv = _sale(scene, payments=[_card("1080.00")])
    items = list(inv.items.all())
    assert sum(i.tax_amount for i in items) == inv.tax_total
    assert sum(i.line_total for i in items) == inv.grand_total
