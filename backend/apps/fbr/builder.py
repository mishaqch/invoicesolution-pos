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
    "PCS":     "Numbers, pieces, units",
    "DOZEN":   "Dozen",
    "PACK":    "Numbers, pieces, units",
    "BOX":     "Numbers, pieces, units",
    "CARTON":  "Numbers, pieces, units",
    "BAG":     "Numbers, pieces, units",
    "BOTTLE":  "Numbers, pieces, units",
    "TIN":     "Numbers, pieces, units",
    "PAIR":    "Numbers, pieces, units",
    "ROLL":    "Numbers, pieces, units",
    "SHEET":   "Numbers, pieces, units",
    "KG":      "Kilograms",
    "GM":      "Grams",
    "MG":      "Milligrams",
    "LTR":     "Liters",
    "ML":      "Milliliters",
    "METER":   "Meters",
    "CM":      "Centimeters",
    "MM":      "Millimeters",
    "SQM":     "Square Meters",
}

INVOICE_TYPE_FBR_MAP: dict[str, str] = {
    "sale": "Sale Invoice",
    "debit_note": "Debit Note",
    "credit_note": "Credit Note",
}


WALK_IN_NTN_CNIC = "0000000000000"  # 13 zeros — PRAL convention.


def map_uom(code: str) -> str:
    """Return the FBR-shaped uoM string. Unknown codes fall back to PCS."""
    return UOM_FBR_MAP.get((code or "").upper(), "Numbers, pieces, units")


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


def _to_money_number(d: Decimal | None) -> float:
    """Money fields go on the wire as numbers (not strings).

    Python's json encoder writes a Decimal via float(), which truncates
    precision; we round to 4dp before that conversion to avoid surprises.
    """
    if d is None:
        return 0
    return float(Decimal(d).quantize(Decimal("0.0001")))


def build_item(item: SaleItem) -> dict[str, Any]:
    qty_dec = item.quantity
    qty_int = qty_dec.to_integral_value() if qty_dec == qty_dec.to_integral() else qty_dec
    return {
        "hsCode": item.hs_code or "",
        "productDescription": item.product_name,
        "rate": format_rate(item.tax_rate),
        "uoM": map_uom(item.uom_code),
        "quantity": float(qty_int) if isinstance(qty_int, Decimal) else int(qty_int),
        "totalValues": _to_money_number(item.line_total),
        "valueSalesExcludingST": _to_money_number(
            item.line_total - item.tax_amount - item.further_tax_amount - item.fed_amount
        ),
        "fixedNotifiedValueOrRetailPrice": _to_money_number(item.fixed_notified_value),
        "salesTaxApplicable": _to_money_number(item.tax_amount),
        "salesTaxWithheldAtSource": _to_money_number(item.st_withheld_amount),
        "extraTax": 0,  # we don't track this separately in V1
        "furtherTax": _to_money_number(item.further_tax_amount),
        "sroScheduleNo": item.sro_schedule_no or "",
        "fedPayable": _to_money_number(item.fed_amount),
        "discount": _to_money_number(item.discount_amount),
        "saleType": item.sale_type or "Goods at standard rate (default)",
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
