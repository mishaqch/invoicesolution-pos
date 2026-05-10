"""Sandbox scenario registry (SN001 … SN015+).

Each scenario builder produces a synthetic invoice payload matching the
description PRAL publishes for that scenario code. Add new scenarios as
PRAL publishes them — one decorator + function.

The actual invoice numbers are synthetic ('SCEN-SN001-…'), so they don't
collide with real customer invoice sequences.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from apps.tenants.models import Tenant


@dataclass
class ScenarioMeta:
    code: str
    description: str
    sectors: tuple[str, ...]
    builder: Callable[[Tenant], dict]


SCENARIOS: dict[str, ScenarioMeta] = {}


def register(code: str, *, description: str, sectors: tuple[str, ...]):
    def decorator(fn: Callable[[Tenant], dict]) -> Callable[[Tenant], dict]:
        SCENARIOS[code] = ScenarioMeta(
            code=code, description=description, sectors=sectors, builder=fn,
        )
        return fn
    return decorator


def eligible_scenarios(tenant: Tenant) -> list[ScenarioMeta]:
    sector = tenant.fbr_sector or "All Other Sectors"
    return [
        s for s in SCENARIOS.values()
        if not s.sectors or sector in s.sectors or "All Other Sectors" in s.sectors
    ]


# ---------------------------------------------------------------------------
# Builders. The synthetic JSON below matches the wire format from the
# v1.6 manual's appendix examples for each scenario.
# ---------------------------------------------------------------------------


def _today() -> str:
    return dt.date.today().isoformat()


def _seller_block(tenant: Tenant) -> dict:
    return {
        "sellerNTNCNIC": tenant.ntn,
        "sellerBusinessName": tenant.business_name,
        "sellerProvince": tenant.province,
        "sellerAddress": tenant.address or "",
    }


@register("SN001",
          description="Goods at standard rate (default) — registered buyer",
          sectors=("All Other Sectors", "FMCG", "Pharmaceuticals", "Mobile"))
def build_sn001(tenant: Tenant) -> dict:
    return {
        "invoiceType": "Sale Invoice",
        "invoiceDate": _today(),
        **_seller_block(tenant),
        "buyerNTNCNIC": "1000000000007",
        "buyerBusinessName": "Test Registered Buyer",
        "buyerProvince": tenant.province,
        "buyerAddress": "Test buyer address",
        "buyerRegistrationType": "Registered",
        "invoiceRefNo": f"SCEN-SN001-{tenant.id.hex[:8]}",
        "scenarioId": "SN001",
        "items": [{
            "hsCode": "1006.3010",
            "productDescription": "Basmati rice 5kg",
            "rate": "18%",
            "uoM": "Kilograms",
            "quantity": 5,
            "totalValues": 1180.00,
            "valueSalesExcludingST": 1000.00,
            "fixedNotifiedValueOrRetailPrice": 0,
            "salesTaxApplicable": 180.00,
            "salesTaxWithheldAtSource": 0,
            "extraTax": 0,
            "furtherTax": 0,
            "sroScheduleNo": "",
            "fedPayable": 0,
            "discount": 0,
            "saleType": "Goods at standard rate (default)",
            "sroItemSerialNo": "",
        }],
    }


@register("SN002",
          description="Goods at standard rate (default) — unregistered buyer",
          sectors=("All Other Sectors", "FMCG"))
def build_sn002(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["buyerNTNCNIC"] = "0000000000000"
    payload["buyerBusinessName"] = "Walk-in Customer"
    payload["buyerRegistrationType"] = "Unregistered"
    payload["invoiceRefNo"] = f"SCEN-SN002-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN002"
    return payload


@register("SN003",
          description="Goods at zero rate (zero-rated supply)",
          sectors=("All Other Sectors", "Pharmaceuticals"))
def build_sn003(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN003-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN003"
    payload["items"][0].update({
        "rate": "0%",
        "salesTaxApplicable": 0,
        "totalValues": 1000.00,
        "saleType": "Goods at zero-rate",
    })
    return payload


@register("SN004",
          description="Goods exempt from sales tax",
          sectors=("All Other Sectors", "Pharmaceuticals"))
def build_sn004(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN004-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN004"
    payload["items"][0].update({
        "rate": "Exempt",
        "salesTaxApplicable": 0,
        "totalValues": 1000.00,
        "saleType": "Exempt goods",
    })
    return payload


@register("SN005",
          description="Goods at reduced rate (8%) — registered buyer",
          sectors=("All Other Sectors",))
def build_sn005(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN005-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN005"
    payload["items"][0].update({
        "rate": "8%",
        "salesTaxApplicable": 80.00,
        "totalValues": 1080.00,
        "saleType": "Goods at reduced rate",
    })
    return payload


@register("SN006",
          description="Goods at higher rate (25%)",
          sectors=("All Other Sectors",))
def build_sn006(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN006-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN006"
    payload["items"][0].update({
        "rate": "25%",
        "salesTaxApplicable": 250.00,
        "totalValues": 1250.00,
    })
    return payload


@register("SN007",
          description="Goods with retail price (Third Schedule)",
          sectors=("FMCG", "All Other Sectors"))
def build_sn007(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN007-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN007"
    payload["items"][0].update({
        "fixedNotifiedValueOrRetailPrice": 1180.00,
        "saleType": "Goods at standard rate (Third Schedule)",
    })
    return payload


@register("SN008",
          description="Sale to non-registered buyer over Rs. 100,000",
          sectors=("All Other Sectors",))
def build_sn008(tenant: Tenant) -> dict:
    payload = build_sn002(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN008-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN008"
    # CNIC is required for unregistered buyers > Rs 100k
    payload["buyerNTNCNIC"] = "3520201234567"
    payload["buyerBusinessName"] = "Bulk-buying Walk-in"
    payload["items"][0].update({
        "totalValues": 118000.00,
        "valueSalesExcludingST": 100000.00,
        "salesTaxApplicable": 18000.00,
        "quantity": 100,
    })
    return payload


@register("SN015",
          description="Mobile phone sale (Third Schedule, fixed retail price)",
          sectors=("Mobile", "All Other Sectors"))
def build_sn015(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN015-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN015"
    payload["items"] = [{
        "hsCode": "8517.1100",
        "productDescription": "Mobile phone",
        "rate": "18%",
        "uoM": "Numbers, pieces, units",
        "quantity": 1,
        "totalValues": 35400.00,
        "valueSalesExcludingST": 30000.00,
        "fixedNotifiedValueOrRetailPrice": 35400.00,
        "salesTaxApplicable": 5400.00,
        "salesTaxWithheldAtSource": 0,
        "extraTax": 0,
        "furtherTax": 0,
        "sroScheduleNo": "",
        "fedPayable": 0,
        "discount": 0,
        "saleType": "Mobile (Third Schedule)",
        "sroItemSerialNo": "",
    }]
    return payload


# ---------------------------------------------------------------------------
# Additional scenarios (SN009 - SN014) added to round out the sector coverage
# called out in the PRAL Digital Invoicing manual. Each follows the SN001
# baseline and overrides only the fields relevant to the case.
# ---------------------------------------------------------------------------


@register("SN009",
          description="Services at standard rate (16%)",
          sectors=("Services", "All Other Sectors"))
def build_sn009(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN009-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN009"
    payload["items"][0].update({
        "hsCode": "9805.0000",
        "productDescription": "Consulting service",
        "rate": "16%",
        "salesTaxApplicable": 160.00,
        "totalValues": 1160.00,
        "saleType": "Services at standard rate",
        "uoM": "Service",
    })
    return payload


@register("SN010",
          description="Services at reduced rate (5%)",
          sectors=("Services", "All Other Sectors"))
def build_sn010(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN010-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN010"
    payload["items"][0].update({
        "hsCode": "9805.0000",
        "productDescription": "Reduced-rate service",
        "rate": "5%",
        "salesTaxApplicable": 50.00,
        "totalValues": 1050.00,
        "saleType": "Services at reduced rate",
        "uoM": "Service",
    })
    return payload


@register("SN011",
          description="Goods with FED in sales-tax mode (16%)",
          sectors=("Telecom", "All Other Sectors"))
def build_sn011(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN011-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN011"
    payload["items"][0].update({
        "rate": "16%",
        "salesTaxApplicable": 160.00,
        "fedPayable": 50.00,
        "totalValues": 1210.00,
        "saleType": "Goods with FED in ST mode",
    })
    return payload


@register("SN012",
          description="Goods with sales tax withheld at source",
          sectors=("All Other Sectors",))
def build_sn012(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN012-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN012"
    payload["items"][0].update({
        "rate": "18%",
        "salesTaxApplicable": 180.00,
        "salesTaxWithheldAtSource": 36.00,   # 1/5 of ST
        "totalValues": 1180.00,
        "saleType": "ST withheld at source",
    })
    return payload


@register("SN013",
          description="Goods at standard rate with extra tax (3%)",
          sectors=("All Other Sectors", "FMCG"))
def build_sn013(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN013-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN013"
    payload["items"][0].update({
        "rate": "18%",
        "salesTaxApplicable": 180.00,
        "extraTax": 30.00,
        "totalValues": 1210.00,
        "saleType": "Goods with extra tax",
    })
    return payload


@register("SN014",
          description="Debit / credit note reference (amendment)",
          sectors=("All Other Sectors",))
def build_sn014(tenant: Tenant) -> dict:
    payload = build_sn001(tenant)
    payload["invoiceRefNo"] = f"SCEN-SN014-{tenant.id.hex[:8]}"
    payload["scenarioId"] = "SN014"
    payload["invoiceType"] = "Debit Note"
    payload["referenceInvoiceNo"] = "SCEN-REF-PLACEHOLDER"
    payload["items"][0].update({
        "rate": "18%",
        "salesTaxApplicable": 18.00,
        "totalValues": 118.00,
        "saleType": "Debit note item",
    })
    return payload
