"""FBR JSON builder — 100% coverage target.

Every gotcha from INTEGRATIONS.md §1.4 has a test:
  * rate is a string like '18%'
  * uoM mapped to PRAL's verbose enum
  * buyerNTNCNIC is '0000000000000' (13 zeros) for walk-ins
  * scenarioId required in sandbox, absent in production
  * money fields are numbers (not strings)
  * invoiceDate is YYYY-MM-DD only
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.builder import (
    WALK_IN_NTN_CNIC,
    build_invoice_payload,
    format_rate,
    map_uom,
)
from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Terminal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Defence", code="DHA",
        address="Plot 45, DHA Phase 5", city="Karachi", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="fbr-test-1",
    )


@pytest.fixture
def product(db, tenant):
    uom = UnitOfMeasure.objects.get(code="KG")
    return Product.objects.create(
        tenant=tenant, name="Basmati rice 5kg", sku="RICE-5", uom=uom,
        sale_price=Decimal("1000"), cost_price=Decimal("700"),
    )


def _invoice_with_one_item(*, tenant, branch, terminal, cashier, product,
                            registered=False, scenario_id=None):
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=cashier,
        local_invoice_number="DHA-T1-2026-0009999",
        invoice_date=dt.date(2026, 5, 9),
        buyer_name="Test Buyer" if registered else None,
        buyer_ntn_cnic="1000000000007" if registered else None,
        buyer_registration_type="Registered" if registered else "Unregistered",
        subtotal=Decimal("1000"), discount_total=Decimal("0"),
        tax_total=Decimal("180"), grand_total=Decimal("1180"),
        paid_total=Decimal("1180"), change_given=Decimal("0"),
        client_uuid="11111111-1111-1111-1111-111111111111",
    )
    SaleItem.objects.create(
        invoice=inv, line_number=1, product=product,
        product_name=product.name, product_sku=product.sku,
        hs_code="1006.3010", uom_code="KG",
        quantity=Decimal("5"), unit_price=Decimal("200"),
        cost_price=product.cost_price,
        tax_rate=Decimal("18"), tax_amount=Decimal("180"),
        line_total=Decimal("1180"),
    )
    return inv


# ---------------------------------------------------------------------------
# format_rate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("inp,expected", [
    (18, "18%"),
    (Decimal("18"), "18%"),
    (Decimal("0"), "0%"),
    (Decimal("8"), "8%"),
    (Decimal("17.5"), "17.5%"),
    (Decimal("18.50"), "18.5%"),  # trailing zeros trimmed
    (Decimal("25"), "25%"),
])
def test_format_rate(inp, expected):
    assert format_rate(inp) == expected


# ---------------------------------------------------------------------------
# map_uom
# ---------------------------------------------------------------------------


def test_map_uom_known():
    # PRAL accepts SHORT fixed strings — "KG" not "Kilograms", "Liter" not
    # "Liters" (the long plural is rejected with errorCode 0099). These track
    # the real /pdi/v1/uom values, not the older long forms.
    assert map_uom("PCS") == "Numbers, pieces, units"
    assert map_uom("KG") == "KG"
    assert map_uom("LTR") == "Liter"
    assert map_uom("DOZEN") == "Dozen"
    # Codes that all collapse to the generic "each" FBR unit, and a remapped one.
    assert map_uom("BOX") == "Numbers, pieces, units"
    assert map_uom("LB") == "Pound"


def test_map_uom_unknown_falls_back_to_pcs():
    assert map_uom("UNKNOWN") == "Numbers, pieces, units"


def test_map_uom_case_insensitive():
    assert map_uom("kg") == "KG"


# ---------------------------------------------------------------------------
# build_invoice_payload
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_payload_unregistered_walk_in_uses_13_zeros(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product, registered=False,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["buyerNTNCNIC"] == "0000000000000"
    assert WALK_IN_NTN_CNIC == "0000000000000"
    assert payload["buyerRegistrationType"] == "Unregistered"
    assert payload["buyerBusinessName"] == "Walk-in Customer"


@pytest.mark.django_db
def test_payload_registered_buyer(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product, registered=True,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["buyerNTNCNIC"] == "1000000000007"
    assert payload["buyerRegistrationType"] == "Registered"


@pytest.mark.django_db
def test_payload_rate_is_string_with_pct_sign(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["items"][0]["rate"] == "18%"
    # Critically: it's a STRING, not a number.
    assert isinstance(payload["items"][0]["rate"], str)


@pytest.mark.django_db
def test_payload_uom_mapped_to_verbose_enum(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["items"][0]["uoM"] == "Kilograms"


@pytest.mark.django_db
def test_payload_money_fields_are_numbers_not_strings(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    item = payload["items"][0]
    assert isinstance(item["totalValues"], (int, float))
    assert isinstance(item["valueSalesExcludingST"], (int, float))
    assert isinstance(item["salesTaxApplicable"], (int, float))


@pytest.mark.django_db
def test_payload_invoice_date_is_yyyy_mm_dd(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["invoiceDate"] == "2026-05-09"
    assert "T" not in payload["invoiceDate"]


@pytest.mark.django_db
def test_payload_sandbox_includes_scenario_id(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["scenarioId"] == "SN001"


@pytest.mark.django_db
def test_payload_production_omits_scenario_id(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    payload = build_invoice_payload(invoice, environment="production")
    assert "scenarioId" not in payload


@pytest.mark.django_db
def test_payload_sandbox_requires_scenario_id(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    with pytest.raises(ValueError, match="scenario_id"):
        build_invoice_payload(invoice, environment="sandbox")


@pytest.mark.django_db
def test_payload_unknown_environment_raises(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    with pytest.raises(ValueError, match="environment"):
        build_invoice_payload(invoice, environment="staging")


@pytest.mark.django_db
def test_payload_excludes_cancelled_items(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    SaleItem.objects.create(
        invoice=invoice, line_number=2, product=product,
        product_name="Cancelled item", product_sku="X",
        uom_code="PCS", quantity=Decimal("1"), unit_price=Decimal("10"),
        line_total=Decimal("10"), is_cancelled=True,
    )
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert len(payload["items"]) == 1


@pytest.mark.django_db
def test_payload_invoice_type_mapped(
    tenant, branch, terminal, owner_user, product,
):
    invoice = _invoice_with_one_item(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        product=product,
    )
    invoice.invoice_type = "credit_note"
    invoice.save(update_fields=["invoice_type"])
    payload = build_invoice_payload(
        invoice, environment="sandbox", scenario_id="SN001",
    )
    assert payload["invoiceType"] == "Credit Note"


@pytest.mark.django_db
def test_all_registered_scenarios_produce_valid_payloads(tenant):
    """Every scenario in the registry must build a payload with the
    fields PRAL requires: invoiceType, sellerNTNCNIC, items, scenarioId.
    """
    from apps.fbr.scenarios import SCENARIOS

    # 15 scenarios documented in the PRAL Digital Invoicing manual v1.6.
    assert len(SCENARIOS) >= 15, (
        f"Expected >=15 scenarios, found {len(SCENARIOS)}: "
        f"{sorted(SCENARIOS.keys())}"
    )

    for code, meta in SCENARIOS.items():
        payload = meta.builder(tenant)
        assert payload["scenarioId"] == code, f"{code} payload mislabelled"
        assert "sellerNTNCNIC" in payload, f"{code} missing sellerNTNCNIC"
        assert "invoiceType" in payload, f"{code} missing invoiceType"
        assert payload.get("items"), f"{code} has no items"
        for idx, item in enumerate(payload["items"]):
            assert "rate" in item, f"{code} item {idx} missing rate"
            assert isinstance(item["rate"], str), (
                f"{code} item {idx} rate must be a string per PRAL spec"
            )
