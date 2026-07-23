"""Local pre-submit check for POS (cloud IMS) invoices.

FBR's / PRA's IMS cloud (Live/PostData) has NO dry-run endpoint — the only call
mints a REAL fiscal number. So for POS invoices we can't ask the authority "is
this valid?" before committing. This module does the next best thing: it runs
every check WE can locally (fields, POS ID, math, tax/UoM/HS/saleType sanity,
buyer id shape) so the common rejects are caught before the operator commits.

It does NOT call FBR/PRA and cannot guarantee acceptance — only the authority
can. Returns a structured result the UI renders as a checklist.
"""
from __future__ import annotations

from decimal import Decimal

from .builder import (
    WALK_IN_NTN_CNIC,
    is_services_hs_code,
    map_uom,
)


# Rates FBR/PRA accept for a services line (chapter-98 HS). 18% is goods-only.
_SERVICES_VALID_RATES = {Decimal("0"), Decimal("5"), Decimal("15"),
                         Decimal("16"), Decimal("17")}


def _issue(severity, field, message):
    return {"severity": severity, "field": field, "message": message}


def precheck_pos_invoice(invoice) -> dict:
    """Return {ok, blocking, issues:[{severity, field, message}]} for a POS
    invoice. severity: "error" (would very likely be rejected) or "warning"
    (allowed, but worth a look). `blocking` is True if any error is present.
    """
    issues: list[dict] = []

    # --- Already fiscalized? nothing to check ---------------------------
    if invoice.fbr_invoice_number:
        return {
            "ok": True, "blocking": False,
            "issues": [_issue("info", "fbr", f"Already fiscalized: FBR #{invoice.fbr_invoice_number}")],
        }

    branch = invoice.branch
    pos_id = getattr(branch, "fbr_pos_id", None)

    # --- POS registration ------------------------------------------------
    if not pos_id:
        issues.append(_issue("error", "pos_id",
                             "This branch has no FBR POS ID. Set it on the Branches page before fiscalizing."))

    # --- Buyer ----------------------------------------------------------
    reg = (invoice.buyer_registration_type or "").lower()
    ntn = (invoice.buyer_ntn_cnic or "").strip()
    if reg == "registered":
        if not ntn or ntn == WALK_IN_NTN_CNIC:
            issues.append(_issue("error", "buyer",
                                 "Buyer is 'Registered' but has no NTN/CNIC. Add the buyer's NTN (7 digits) or CNIC (13 digits)."))
        elif len(ntn.replace("-", "")) not in (7, 13):
            issues.append(_issue("warning", "buyer",
                                 f"Buyer NTN/CNIC '{ntn}' isn't 7 (NTN) or 13 (CNIC) digits — FBR may reject it."))
    # Walk-in: NTN blank/zeros is fine (server sends 13 zeros).

    # --- Items ----------------------------------------------------------
    items = [it for it in invoice.items.all() if not getattr(it, "is_cancelled", False)]
    if not items:
        issues.append(_issue("error", "items", "The invoice has no active line items."))

    for idx, it in enumerate(items, start=1):
        tag = f"item {idx} ({it.product_name})"
        # Quantity / price
        if (it.quantity or 0) <= 0:
            issues.append(_issue("error", tag, "Quantity must be greater than 0."))
        if (it.unit_price or 0) < 0:
            issues.append(_issue("error", tag, "Unit price can't be negative."))

        # Line math: line_total should ≈ qty*unit_price + tax (2dp tolerance).
        rate = Decimal(it.tax_rate or 0)
        net = (Decimal(it.line_total or 0) - Decimal(it.tax_amount or 0))
        expected_tax = (net * rate / Decimal(100))
        if abs(expected_tax - Decimal(it.tax_amount or 0)) > Decimal("0.5"):
            issues.append(_issue("warning", tag,
                                 f"Tax {it.tax_amount} doesn't match {rate}% of {net} (≈{expected_tax:.2f})."))

        # UoM must map to a real FBR unit.
        if not (it.uom_code or "").strip():
            issues.append(_issue("error", tag, "Unit of measure is missing."))

        # Services (HS chapter 98): must be a services-valid rate + Others UoM.
        if is_services_hs_code(it.hs_code):
            if rate not in _SERVICES_VALID_RATES:
                issues.append(_issue("error", tag,
                                     f"Services HS code {it.hs_code} can't use {rate}% — use 0/5/15/16/17% (16% is typical). 18% is goods-only."))
            if map_uom(it.uom_code) != "Others":
                issues.append(_issue("warning", tag,
                                     "Services lines use UoM 'Others' — the server sends that automatically, but the product's UoM differs."))

    # --- Totals reconcile ------------------------------------------------
    live_grand = sum((Decimal(it.line_total or 0) for it in items), Decimal("0"))
    if abs(live_grand - Decimal(invoice.grand_total or 0)) > Decimal("0.5"):
        issues.append(_issue("warning", "totals",
                             f"Invoice grand total {invoice.grand_total} doesn't match the sum of live items ({live_grand})."))

    blocking = any(i["severity"] == "error" for i in issues)
    return {"ok": not blocking, "blocking": blocking, "issues": issues}
