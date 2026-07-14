"""FBR / PRAL JSON builder.

Single source of truth for the wire format. Every gotcha from
INTEGRATIONS.md §1.4 is encoded here:

  - rate is a string like "18%", not a number.
  - uoM is a verbose enum string ("Numbers, pieces, units"), mapped from
    our short codes (PCS, KG, …).
  - buyerNTNCNIC is "0000000000000" (13 zeros) for unregistered walk-ins.
  - scenarioId is REQUIRED in sandbox, OMITTED in production.
  - All money fields are numbers in PKR (not paisa, not strings).
  - invoiceDate is YYYY-MM-DD only, no time.

100% test coverage on this module is a hard requirement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.sales.models import Invoice, SaleItem
from apps.tenants.models import Branch, Tenant


# ---------------------------------------------------------------------------
# UoM map — our short codes → PRAL's verbose enum strings.
#
# Source: PRAL Digital Invoicing v1.6 manual + the hs_codes_seed.json uoms
# we ship. As new codes appear, add a row here. UNKNOWN → fallback to
# "Numbers, pieces, units" (the safest default for general retail).
# ---------------------------------------------------------------------------

UOM_FBR_MAP: dict[str, str] = {
    # Local code → exact PRAL UoM string.
    #
    # Source of truth: GET https://gw.fbr.gov.pk/pdi/v1/uom
    # PRAL accepts short, fixed strings — "KG" not "Kilograms",
    # "Liter" not "Liters", "Meter" not "Meters". Sending the long
    # plural form gets rejected with errorCode 0099 ("Provided UoM is
    # not allowed against the provided HS Code"), even when the UoM
    # is otherwise valid for that HS row.
    "PCS":     "Numbers, pieces, units",
    "DOZEN":   "Dozen",
    "PACK":    "Packs",
    "BOX":     "Numbers, pieces, units",
    "CARTON":  "Numbers, pieces, units",
    "BAG":     "Bag",
    "BOTTLE":  "Numbers, pieces, units",
    "TIN":     "Numbers, pieces, units",
    "PAIR":    "Pair",
    "ROLL":    "Numbers, pieces, units",
    "SHEET":   "Numbers, pieces, units",
    "KG":      "KG",
    "GM":      "Gram",
    "MG":      "Gram",          # PRAL has no mg row; round up.
    "LTR":     "Liter",
    "LITER":   "Liter",
    "ML":      "Liter",         # PRAL has no ml row; aggregate.
    "METER":   "Meter",
    "M":       "Meter",
    "CM":      "Meter",
    "MM":      "Meter",
    "SQM":     "Square Metre",
    "SQF":     "Square Foot",
    "SQFT":    "Square Foot",
    "FT":      "Square Foot",   # PRAL has no linear-foot row; closest is sq ft.
    "SQY":     "SqY",
    "MT":      "MT",            # metric ton
    "40KG":    "40KG",
    "CUBIC_M": "Cubic Metre",
    "CBM":     "Cubic Metre",
    "GALLON":  "Gallon",
    "POUND":   "Pound",
    "LB":      "Pound",
    "CARAT":   "Carat",
    "KWH":     "KWH",
    "MWH":     "1000 kWh",
    "MW":      "Mega Watt",
    "MMBTU":   "MMBTU",
    "BBL":     "Barrels",
    "BOL":     "Bill of lading",
    "LOGS":    "Timber Logs",
    "1000U":   "Thousand Unit",
    # Generic / unmapped local codes that legitimately mean "each":
    "NO":      "NO",
    "SET":     "SET",
    # "OTHER" maps to PRAL's literal "Others" unit — REQUIRED for services
    # (HS chapter 98): PRAL rejects "Numbers, pieces, units" on a services HS
    # code with 0099, but accepts "Others". (Confirmed against the sandbox
    # validator for HS 9819.1300.)
    "OTHER":   "Others",
}

INVOICE_TYPE_FBR_MAP: dict[str, str] = {
    "sale": "Sale Invoice",
    "debit_note": "Debit Note",
    "credit_note": "Credit Note",
}


WALK_IN_NTN_CNIC = "0000000000000"  # 13 zeros — PRAL convention.


# Friendly DISPLAY label for each FBR uoM string — shown in the product/invoice
# UoM dropdowns. This is presentation ONLY: the value actually submitted to FBR
# is the UOM_FBR_MAP string (the key here), never this label. So "KG" is shown
# as "Kilogram" but still sent to PRAL as "KG". Any FBR string without an entry
# here displays as-is (e.g. "Dozen", "Bag", "Gram", "Numbers, pieces, units").
UOM_DISPLAY_LABELS: dict[str, str] = {
    "KG":            "Kilogram",
    "MT":            "Metric Ton",
    "40KG":          "40 KG",
    "SqY":           "Square Yard",
    "KWH":           "Kilowatt Hour (kWh)",
    "MMBTU":         "Million BTU (MMBTU)",
    "1000 kWh":      "1000 kWh",
    "Mega Watt":     "Mega Watt (MW)",
    "Others":        "Others (services)",
}


def map_uom(code: str) -> str:
    """Return the FBR-shaped uoM string. Unknown codes fall back to PCS."""
    return UOM_FBR_MAP.get((code or "").upper(), "Numbers, pieces, units")


def uom_display_label(code: str) -> str:
    """Friendly label for a UoM code's FBR unit (presentation only)."""
    fbr = map_uom(code)
    return UOM_DISPLAY_LABELS.get(fbr, fbr)


def format_rate(percentage: Decimal | str | int | float) -> str:
    """Format a percentage as the PRAL-shaped string '<n>%'.

    Trims trailing zeros after the decimal: 18 → '18%', 18.50 → '18.5%'.
    """
    d = Decimal(str(percentage))
    # Normalize to remove trailing zeros, but keep an integer if whole.
    normalized = d.normalize()
    # Decimal.normalize() of 18 is '1.8E+1'; convert via integer/Decimal.
    if normalized == normalized.to_integral():
        return f"{int(normalized)}%"
    return f"{normalized:f}%"


def format_line_rate(percentage, sale_type: str | None) -> str:
    """The PRAL `rate` string for a line, given its saleType.

    Most sale types use the numeric percentage ("18%", "1%", "0%"), BUT exempt
    goods must send the literal "Exempt" — PRAL rejects "0%" for an
    "Exempt goods" line with errorCode 0046 ("Provided Rate is not correct for
    selected Sales Type"). Zero-rated goods keep "0%" (saleType
    "Goods at zero-rate"). This matches the SN006/SN007 scenario payloads.
    """
    if (sale_type or "").strip().lower() == "exempt goods":
        return "Exempt"
    return format_rate(percentage)


def _to_money_number(d: Decimal | None) -> float:
    """Money fields go on the wire as numbers (not strings).

    PRAL's wire spec limits numeric fields to 2 decimal places (the
    only 4-dp field is `quantity`). Sending more than 2 dp gets the
    invoice rejected with errorCode 0302 — "Please provide numeric
    values with up to 2 decimal places". We round HALF-UP to 2 dp.

    We previously rounded to 4 dp here, which was wrong for money
    fields and tripped the 0302 rule whenever 3rd-Schedule reverse-
    math produced an awkward remainder (e.g. 800 / 1.18 = 677.9661).
    """
    if d is None:
        return 0
    return float(Decimal(d).quantize(Decimal("0.01")))


# Services HS codes in PRAL live under chapter 98 (98xx.xxxx — "SERVICES
# PROVIDED OR RENDERED BY SPECIFIED PERSONS"). A services line has three FBR
# requirements that differ from goods, all confirmed against the sandbox
# validator for HS 9819.1300 (commission agents):
#   - saleType MUST be "Services" (not "Goods at standard rate (default)")
#   - uoM MUST be "Others"  (PRAL rejects "Numbers, pieces, units" here → 0099)
#   - rate must be a services-valid rate (0/Exempt/5/15/16/17%) — NOT 18%,
#     which is goods-only (→ 0046). We don't force the percentage (the operator
#     sets it), but 18% on a service will still be rejected by PRAL by design.
# Sandbox scenario for services is SN019 (see _scenario_for_item).
SERVICES_SALE_TYPE = "Services"
SERVICES_UOM_FBR = "Others"


def is_services_hs_code(hs_code: str | None) -> bool:
    """True if the HS code is a PRAL services code (chapter 98)."""
    return (hs_code or "").strip().startswith("98")


def build_item(item: SaleItem) -> dict[str, Any]:
    qty_dec = item.quantity
    qty_int = qty_dec.to_integral_value() if qty_dec == qty_dec.to_integral() else qty_dec

    # 3rd-Schedule (retail-price-fixed) lines have different math: tax is
    # charged ON the MRP for the given rate, not extracted from it as
    # tax-inclusive. This is the PRAL rule (settled across sandbox iterations —
    # see scenarios.build_sn008) and the literal text of errorCode 0102:
    # "the Fixed/Notified Value or Retail Price is used to calculate the Sales
    # Tax Amount for the provided rate."
    #   fixedNotifiedValueOrRetailPrice = retail_price * qty   (the MRP base)
    #   salesTaxApplicable              = retail * rate / 100  (tax ON retail)
    #   valueSalesExcludingST           = retail               (full retail —
    #                                     PRAL rejects 0/empty here; do NOT
    #                                     divide by (1+rate) — that gave 0102)
    #   totalValues                     = retail + salesTaxApplicable
    # The on-receipt totals (line_total + tax_amount on the SaleItem) remain
    # untouched — they're what the customer paid. These are FBR's view.
    is_retail_priced = (
        item.fixed_notified_value is not None
        and item.fixed_notified_value > 0
    )
    if is_retail_priced:
        retail_total = Decimal(item.fixed_notified_value)
        rate_pct = Decimal(item.tax_rate or 0)
        sales_tax = (retail_total * rate_pct / Decimal(100))
        value_excl_st = retail_total
        total_values = retail_total + sales_tax
        sale_type = item.sale_type or "3rd Schedule Goods"
    else:
        value_excl_st = (
            item.line_total - item.tax_amount
            - item.further_tax_amount - item.fed_amount
        )
        sales_tax = item.tax_amount
        total_values = item.line_total
        sale_type = item.sale_type or "Goods at standard rate (default)"

    # Services (HS chapter 98): PRAL requires saleType "Services" and uoM
    # "Others". Apply these unless the operator explicitly chose a different,
    # services-appropriate sale type (e.g. "Services (FED in ST Mode)"). We
    # only auto-set when the sale type is unset or the goods default — never
    # clobber a deliberate services variant.
    services = is_services_hs_code(item.hs_code)
    if services and (not item.sale_type or "goods" in sale_type.lower()):
        sale_type = SERVICES_SALE_TYPE
    # uoM: "Others" for services, unless the product carries a UoM that already
    # maps to a services-valid string the operator set on purpose.
    uom_fbr = SERVICES_UOM_FBR if services else map_uom(item.uom_code)

    return {
        "hsCode": item.hs_code or "",
        "productDescription": item.product_name,
        "rate": format_line_rate(item.tax_rate, sale_type),
        "uoM": uom_fbr,
        "quantity": float(qty_int) if isinstance(qty_int, Decimal) else int(qty_int),
        "totalValues": _to_money_number(total_values),
        "valueSalesExcludingST": _to_money_number(value_excl_st),
        "fixedNotifiedValueOrRetailPrice": _to_money_number(item.fixed_notified_value),
        "salesTaxApplicable": _to_money_number(sales_tax),
        "salesTaxWithheldAtSource": _to_money_number(item.st_withheld_amount),
        # FBR's published spec shows extraTax as an empty string ""
        # (unlike the other numeric tax fields). We don't track it
        # separately in V1, so always send "" — matches the spec
        # exactly and PRAL accepts it either as number or string.
        "extraTax": "",
        "furtherTax": _to_money_number(item.further_tax_amount),
        "sroScheduleNo": item.sro_schedule_no or "",
        "fedPayable": _to_money_number(item.fed_amount),
        "discount": _to_money_number(item.discount_amount),
        "saleType": sale_type,
        "sroItemSerialNo": item.sro_item_serial_no or "",
    }


def build_invoice_payload(
    invoice: Invoice,
    *,
    environment: str,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    """Build the PRAL wire-format payload for a single invoice.

    Args:
        invoice: the persisted Invoice (with items prefetched).
        environment: 'sandbox' | 'production'. Determines whether
            scenarioId is included.
        scenario_id: required iff environment == 'sandbox'.
    """
    if environment not in ("sandbox", "production"):
        raise ValueError(f"unknown environment: {environment}")
    if environment == "sandbox" and not scenario_id:
        raise ValueError("scenario_id is required in sandbox environment")

    tenant: Tenant = invoice.tenant
    branch: Branch = invoice.branch

    # Buyer snapshot is already on the invoice; fall back to walk-in defaults.
    buyer_ntn_cnic = invoice.buyer_ntn_cnic or WALK_IN_NTN_CNIC
    buyer_registration_type = invoice.buyer_registration_type or "Unregistered"

    payload: dict[str, Any] = {
        "invoiceType": INVOICE_TYPE_FBR_MAP[invoice.invoice_type],
        "invoiceDate": invoice.invoice_date.isoformat(),
        "sellerNTNCNIC": tenant.ntn,
        "sellerBusinessName": tenant.business_name,
        "sellerProvince": tenant.province,
        "sellerAddress": branch.address,
        "buyerNTNCNIC": buyer_ntn_cnic,
        "buyerBusinessName": invoice.buyer_name or "Walk-in Customer",
        "buyerProvince": invoice.buyer_province or tenant.province,
        "buyerAddress": invoice.buyer_address or "",
        "buyerRegistrationType": buyer_registration_type,
        "invoiceRefNo": invoice.local_invoice_number,
        "items": [
            build_item(item)
            for item in invoice.items.all().order_by("line_number")
            if not item.is_cancelled
        ],
    }

    # Phase 6 — credit/debit notes reference the original invoice's FBR
    # number so PRAL can link them. The field name `referenceInvoiceNo`
    # follows the v1.6 manual; if PRAL diverges we adjust here only.
    if invoice.invoice_type in ("credit_note", "debit_note") and invoice.reference_invoice_id:
        ref = (
            type(invoice).objects
            .only("fbr_invoice_number", "local_invoice_number")
            .get(pk=invoice.reference_invoice_id)
        )
        payload["referenceInvoiceNo"] = (
            ref.fbr_invoice_number or ref.local_invoice_number
        )

    if environment == "sandbox":
        payload["scenarioId"] = scenario_id
    # In production, we deliberately do NOT include scenarioId — per §1.4
    # gotcha, "omit or empty for production". An empty string is also
    # accepted but the manual prefers omission.

    return payload
