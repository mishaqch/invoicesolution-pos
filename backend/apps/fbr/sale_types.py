"""Canonical FBR/PRAL Sale Types (transtypecode) — single source of truth.

`saleType` is the per-line transaction-type classification FBR uses to decide
how an item is taxed (standard, 3rd Schedule on retail price, reduced, zero,
exempt, sector-specific…). It MUST match PRAL's /pdi/v1/transtypecode list
VERBATIM — exact casing and punctuation — or PRAL rejects the invoice with
errorCode 0204 ("Sale type not match…").

The values below are the strings already proven against real PRAL in
apps/fbr/scenarios.py. This module centralises them so the Product field, the
API, validation, and the builder all reference ONE list (mirrors how
builder.UOM_FBR_MAP centralises units).

Wire-format trap: "Goods as per SRO.297(|)/2023" contains a PIPE character
(|), not the letter I or l. Keep it byte-for-byte.
"""

from __future__ import annotations

DEFAULT_SALE_TYPE = "Goods at standard rate (default)"

# The exact /pdi/v1/transtypecode strings. Order here is not significant —
# the API orders for display via sale_type_options().
SALE_TYPES: tuple[str, ...] = (
    "Goods at standard rate (default)",
    "3rd Schedule Goods",
    "Goods at Reduced Rate",
    "Goods at zero-rate",
    "Exempt goods",
    "Electric Vehicle",
    "Mobile Phones",
    "Cement /Concrete Block",
    "Potassium Chlorate",
    "CNG Sales",
    "Gas to CNG stations",
    "Telecommunication services",
    "Steel melting and re-rolling",
    "Ship breaking",
    "Cotton ginners",
    "Petroleum Products",
    "Processing/Conversion of Goods",
    "Goods (FED in ST Mode)",
    "Services (FED in ST Mode)",
    "Services",
    "Electricity Supply to Retailers",
    "Toll Manufacturing",
    "Non-Adjustable Supplies",
    "Goods as per SRO.297(|)/2023",  # NB: PIPE char (|), not I/l.
)

# O(1) validation set — guards the serializer + checkout so a stale/free-typed
# string can never reach PRAL.
SALE_TYPE_SET = frozenset(SALE_TYPES)

# Friendly DISPLAY label per verbatim value (presentation only — the submitted
# saleType is always the verbatim key, never this label). Anything without an
# entry displays as its verbatim value.
SALE_TYPE_DISPLAY_LABELS: dict[str, str] = {
    "Goods at standard rate (default)": "Standard rate (general goods)",
    "3rd Schedule Goods":               "3rd Schedule (taxed on retail price)",
    "Goods at Reduced Rate":            "Reduced rate (8th Schedule)",
    "Goods at zero-rate":               "Zero-rated (5th Schedule)",
    "Exempt goods":                     "Exempt (6th Schedule)",
    "Electric Vehicle":                 "Electric Vehicle",
    "Mobile Phones":                    "Mobile Phones (9th Schedule)",
    "Goods (FED in ST Mode)":           "Goods — FED in ST mode",
    "Services (FED in ST Mode)":        "Services — FED in ST mode",
    "Goods as per SRO.297(|)/2023":     "Goods per SRO.297(|)/2023",
}

# The handful retailers actually use go in "common"; the rest are
# sector-specific and grouped under "specialised" in the dropdown.
_COMMON = {
    "Goods at standard rate (default)",
    "3rd Schedule Goods",
    "Goods at Reduced Rate",
    "Goods at zero-rate",
    "Exempt goods",
    "Electric Vehicle",
    "Mobile Phones",
}


def sale_type_label(value: str) -> str:
    """Friendly display label for a saleType (presentation only)."""
    return SALE_TYPE_DISPLAY_LABELS.get(value, value)


def sale_type_group(value: str) -> str:
    return "common" if value in _COMMON else "specialised"


def is_valid_sale_type(value: str | None) -> bool:
    return value in SALE_TYPE_SET


def sale_type_options() -> list[dict]:
    """[{value, label, group}] for the API — common first (in the curated
    order above), then specialised alphabetically by label."""
    common = [v for v in SALE_TYPES if v in _COMMON]
    specialised = sorted(
        (v for v in SALE_TYPES if v not in _COMMON),
        key=sale_type_label,
    )
    return [
        {"value": v, "label": sale_type_label(v), "group": sale_type_group(v)}
        for v in (*common, *specialised)
    ]
