"""FBR Sale Type flows Product → SaleItem → builder payload verbatim.

saleType must reach PRAL byte-for-byte (errorCode 0204 on mismatch), so these
assert the exact strings — including the SRO.297 PIPE character — survive the
whole chain, plus the line-override precedence and the 3rd-Schedule coupling.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.builder import build_item
from apps.fbr.sale_types import SALE_TYPES, is_valid_sale_type, sale_type_options
from apps.sales.services import checkout
from apps.tenants.models import Branch, Terminal


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MN", address="x", city="Karachi", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1", device_fingerprint="fp-st-1",
    )


def _product(tenant, *, sale_type="Goods at standard rate (default)", third=False, retail=None,
             sro_schedule="", sro_serial=""):
    uom = UnitOfMeasure.objects.get(code="PCS")
    return Product.objects.create(
        tenant=tenant, name="X", sku=f"X-{uuid.uuid4().hex[:8]}", uom=uom,
        sale_price=Decimal("100"), is_taxable=True, sale_type=sale_type,
        is_third_schedule=third, retail_price=retail,
        sro_schedule_no=sro_schedule, sro_item_serial_no=sro_serial,
    )


def _sale(tenant, branch, terminal, owner_user, product, *, line_sale_type=None):
    line = {
        "product": str(product.id), "quantity": "1", "unit_price": "100",
        "tax_rate": "18", "is_taxable": True,
    }
    if line_sale_type is not None:
        line["sale_type"] = line_sale_type
    return checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[line],
        payments=[{"payment_method": "cash", "amount": "118"}],
        client_uuid=str(uuid.uuid4()),
    )


# --- canonical list -------------------------------------------------------


def test_sale_type_options_complete_and_pipe_intact():
    opts = sale_type_options()
    assert len(opts) == len(SALE_TYPES) == 24
    # The SRO.297 value keeps its PIPE character (not letter I/l).
    assert any(o["value"] == "Goods as per SRO.297(|)/2023" for o in opts)
    # Common group is non-empty and standard rate is first.
    assert opts[0]["value"] == "Goods at standard rate (default)"
    assert is_valid_sale_type("Exempt goods")
    assert not is_valid_sale_type("Made up type")


# --- product → SaleItem ---------------------------------------------------


def test_product_sale_type_flows_to_sale_item(db, tenant, branch, terminal, owner_user):
    p = _product(tenant, sale_type="Exempt goods")
    inv = _sale(tenant, branch, terminal, owner_user, p)
    assert inv.items.first().sale_type == "Exempt goods"


def test_default_product_is_standard_rate(db, tenant, branch, terminal, owner_user):
    p = _product(tenant)  # default
    inv = _sale(tenant, branch, terminal, owner_user, p)
    assert inv.items.first().sale_type == "Goods at standard rate (default)"


def test_line_override_beats_product(db, tenant, branch, terminal, owner_user):
    p = _product(tenant, sale_type="Goods at standard rate (default)")
    inv = _sale(tenant, branch, terminal, owner_user, p, line_sale_type="Goods at zero-rate")
    assert inv.items.first().sale_type == "Goods at zero-rate"


def test_invalid_line_override_falls_back_to_product(db, tenant, branch, terminal, owner_user):
    p = _product(tenant, sale_type="Exempt goods")
    inv = _sale(tenant, branch, terminal, owner_user, p, line_sale_type="garbage")
    assert inv.items.first().sale_type == "Exempt goods"


def test_pipe_char_sale_type_survives_to_builder(db, tenant, branch, terminal, owner_user):
    p = _product(tenant, sale_type="Goods as per SRO.297(|)/2023")
    inv = _sale(tenant, branch, terminal, owner_user, p)
    item = inv.items.first()
    assert item.sale_type == "Goods as per SRO.297(|)/2023"
    # And it reaches the FBR payload byte-for-byte.
    payload = build_item(item)
    assert payload["saleType"] == "Goods as per SRO.297(|)/2023"


def test_third_schedule_sale_type_snapshots_retail(db, tenant, branch, terminal, owner_user):
    p = _product(tenant, sale_type="3rd Schedule Goods", third=True, retail=Decimal("250"))
    inv = _sale(tenant, branch, terminal, owner_user, p)
    item = inv.items.first()
    assert item.sale_type == "3rd Schedule Goods"
    # retail_price * qty was snapshotted onto the line for the FBR retail math.
    assert item.fixed_notified_value == Decimal("250")


def test_third_schedule_tax_computed_on_retail_not_inclusive(db, tenant, branch, terminal, owner_user):
    """Regression for PRAL errorCode 0102. 3rd-Schedule tax = retail * rate / 100
    (tax charged ON the retail price), NOT extracted as tax-inclusive
    (retail/(1+rate)). The inclusive math sent 15.25 for a 100 retail @18% and
    PRAL rejected it; the correct value is 18.00."""
    p = _product(tenant, sale_type="3rd Schedule Goods", third=True, retail=Decimal("100"))
    inv = _sale(tenant, branch, terminal, owner_user, p)
    payload = build_item(inv.items.first())
    assert payload["fixedNotifiedValueOrRetailPrice"] == 100.0
    assert payload["rate"] == "18%"
    assert payload["salesTaxApplicable"] == 18.0          # 100 * 18% — matches PRAL
    assert payload["valueSalesExcludingST"] == 100.0       # full retail, NOT 84.75
    assert payload["totalValues"] == 118.0                 # retail + tax


def test_reduced_rate_sro_flows_product_to_builder(db, tenant, branch, terminal, owner_user):
    """Reduced-rate (8th Schedule): the product's SRO schedule + serial must
    reach the FBR payload, or PRAL rejects the line."""
    p = _product(
        tenant, sale_type="Goods at Reduced Rate",
        sro_schedule="EIGHTH SCHEDULE Table 1", sro_serial="70",
    )
    inv = _sale(tenant, branch, terminal, owner_user, p)
    item = inv.items.first()
    assert item.sale_type == "Goods at Reduced Rate"
    assert item.sro_schedule_no == "EIGHTH SCHEDULE Table 1"
    assert item.sro_item_serial_no == "70"
    payload = build_item(item)
    assert payload["sroScheduleNo"] == "EIGHTH SCHEDULE Table 1"
    assert payload["sroItemSerialNo"] == "70"
    # extraTax must be empty string for reduced-rate (PRAL rejects 0).
    assert payload["extraTax"] == ""
