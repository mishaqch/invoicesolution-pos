"""Sandbox scenario registry (SN001 … SN028).

Each scenario builder produces a synthetic invoice payload matching
PRAL's exact spec for that scenarioId code. Authoritative reference:

  - eyeconconsultant.com/fbr-einvoice-scenario-testing-guide
    (cross-references PRAL's manual against real sandbox behaviour)
  - PRAL Digital Invoicing Technical Documentation v1.6, Annexure A
  - /pdi/v1/transtypecode (live PRAL endpoint for saleType strings)

Wire-format quirks (learned the hard way against real PRAL):

  - uoM is the *short* string from /pdi/v1/uom: "KG", not "Kilograms";
    "Numbers, pieces, units" not "PCS".
  - hsCode must exist in /pdi/v1/itemdesccode. Generic Pakistan
    customs HS codes do NOT all exist there.
  - rate is a string. Standard goods use "18%"; reduced "1%";
    "Exempt" / "0%" for non-taxable; "Rs.3 per unit" for per-unit fixed.
  - saleType must match /pdi/v1/transtypecode VERBATIM — including
    weird capitalisation and punctuation. Mismatch → errorCode 0204
    "Sale type not match with provided scenario No. SN…".
  - extraTax field: MUST be empty string "" (not 0) for reduced-rate
    scenarios SN005 + SN028. Sending 0 trips errorCode 0091.
  - For 3rd-Schedule lines (SN008/SN027): tax is computed on
    fixedNotifiedValueOrRetailPrice, not on valueSalesExcludingST.
  - For SN024: saleType has a PIPE character not letter I —
    "Goods as per SRO.297(|)/2023" — PRAL is strict about it.
  - For registered-buyer scenarios PRAL requires a real registered
    buyer NTN. The docs reference "1000000000007" but that NTN is
    NOT accepted in the current sandbox under all tokens. Operator
    pastes a partner-business NTN into tenant.fbr_test_buyer_ntn.
    Self-billing (buyer NTN == seller NTN) is rejected with 0058.

The actual invoice numbers are synthetic ('SCEN-SN001-…'), so they
don't collide with real customer invoice sequences.
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
    needs_registered_buyer: bool = False


SCENARIOS: dict[str, ScenarioMeta] = {}


def register(
    code: str,
    *,
    description: str,
    sectors: tuple[str, ...],
    needs_registered_buyer: bool = False,
):
    def decorator(fn: Callable[[Tenant], dict]) -> Callable[[Tenant], dict]:
        SCENARIOS[code] = ScenarioMeta(
            code=code, description=description, sectors=sectors,
            builder=fn,
            needs_registered_buyer=needs_registered_buyer,
        )
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Known FBR scenarios — full catalog (separate from SCENARIOS above)
# ---------------------------------------------------------------------------
#
# Why a separate dict: IRIS may assign a scenario to a tenant for which we
# don't yet ship a payload-builder. We still want the operator to SEE that
# code in the tenant-assignment grid + know what it means. (As of 2026-05-28
# all SN001–SN028 have builders, including the retail SN026/SN027/SN028 — but
# the split is kept so a future FBR-added code degrades gracefully.)
#
# SCENARIOS above = subset with a working builder (decorator-populated
#   at import time)
# KNOWN_SCENARIO_META below = every code FBR's manual lists, builder
#   or not. The Tenant admin's assignment grid iterates over THIS dict.
#
# When a scenario is in KNOWN_SCENARIO_META but NOT in SCENARIOS, the
# runner skips it with status="not_implemented" and the UI shows
# "Not yet supported" (instead of pretending it failed).
#
# Source: FBR Digital Invoicing Technical Documentation v1.6, Annexure A.
# Update when FBR publishes a new manual revision.

KNOWN_SCENARIO_META: dict[str, str] = {
    # Catalogue rewritten 2026-05-28 against eyeconconsultant's FBR
    # e-Invoice Scenario Testing Guide — the most accurate public
    # cross-reference of saleType / sroSchedule / extraTax rules per
    # scenarioId. Descriptions match the guide's titles verbatim so
    # super-admin can paste codes from IRIS and visually verify.
    "SN001": "Standard Rate Goods to Registered Buyers",
    "SN002": "Standard Rate Goods to Unregistered Buyers",
    "SN003": "Steel (Melted / Re-Rolled)",
    "SN004": "Steel Scrap by Ship Breakers",
    "SN005": "Reduced Rate Goods (8th Schedule)",
    "SN006": "Exempt Goods (6th Schedule)",
    "SN007": "Zero-Rated Goods (5th Schedule)",
    "SN008": "3rd Schedule Goods",
    "SN009": "Purchase from Cotton Ginners",
    "SN010": "Telecom Services by Mobile Operators",
    "SN011": "Steel via Toll Manufacturing",
    "SN012": "Petroleum Products",
    "SN013": "Electricity to Retailers",
    "SN014": "Gas to CNG Stations",
    "SN015": "Mobile Phones",
    "SN016": "Processing / Conversion of Goods",
    "SN017": "Goods (FED in ST Mode)",
    "SN018": "Services (FED in ST Mode)",
    "SN019": "Services (ICT Ordinance)",
    "SN020": "Electric Vehicles",
    "SN021": "Cement / Concrete Block",
    "SN022": "Potassium Chlorate",
    "SN023": "CNG Sales",
    "SN024": "Goods per SRO 297(I)/2023",
    "SN025": "Drugs (8th Schedule Serial 81)",
    "SN026": "Standard Rate to End Consumers (Retailers)",
    "SN027": "3rd Schedule to End Consumers (Retailers)",
    "SN028": "Reduced Rate to End Consumers (Retailers)",
}


def known_scenario_codes() -> list[str]:
    """All scenario codes IRIS might assign — used by the admin grid."""
    return sorted(KNOWN_SCENARIO_META.keys())


def scenario_description(code: str) -> str:
    """Human description for a code, even if no builder is registered.
    Falls back to '(unknown scenario)' for codes we've never heard of —
    surfaces operator typos in the assignment grid."""
    if code in SCENARIOS:
        return SCENARIOS[code].description
    return KNOWN_SCENARIO_META.get(code, "(unknown scenario)")


def builder_available(code: str) -> bool:
    """Whether we have a payload-builder for `code`. False means the
    code is known in the FBR catalog but our runner can't test it yet
    — operator sees 'Not yet supported' in the UI rather than a
    cryptic failure."""
    return code in SCENARIOS


# ---------------------------------------------------------------------------
# (Business Nature × Sector) → eligible scenarios
# ---------------------------------------------------------------------------
#
# PRAL does NOT expose a per-tenant scenario list via API. We probed
# every plausible endpoint (/pdi/v1/scenarios, /pdi/v1/profile, etc.)
# — all 404. The mapping lives only in FBR's PDF manual ("Digital
# Invoicing — Technical Documentation v1.6 §4, Annexure A").
#
# Our local map below encodes that table. When FBR publishes a new
# manual version, update this dict in a PR and re-run the affected
# tenants' scenario tests. Same versioning discipline as the catalog.
#
# Lookup priority:
#   1. (business_nature, sector) exact match
#   2. (business_nature, "*")     wildcard sector for that nature
#   3. ("*", sector)              wildcard nature for that sector
#   4. ("*", "*")                 last-resort default
#
# A tenant with multiple business natures (e.g. Wholesaler +
# Distributor + Retailer) gets the UNION of all their natures'
# scenarios. That's intentional — a business that wholesales AND
# retails has to demonstrate both flows.

ELIGIBLE_BY_NATURE_AND_SECTOR: dict[tuple[str, str], tuple[str, ...]] = {
    # Aligned with the eyeconconsultant guide (2026-05-28). The real
    # source of truth is the tenant's IRIS-assigned list pasted into
    # tenant.assigned_scenarios; this table is just the fallback when
    # IRIS list is unknown. Best-guess: the basic standard-rate +
    # retail-flow scenarios that almost every tenant gets.
    ("Retailer",    "All Other Sectors"):    ("SN001", "SN002", "SN008", "SN026"),
    ("Retailer",    "Wholesale / Retails"):  ("SN001", "SN002", "SN008", "SN026"),
    ("Wholesaler",  "All Other Sectors"):    ("SN001", "SN002", "SN008"),
    ("Wholesaler",  "Wholesale / Retails"):  ("SN001", "SN002", "SN008"),
    ("Distributor", "All Other Sectors"):    ("SN001", "SN002", "SN008"),
    ("Distributor", "Wholesale / Retails"):  ("SN001", "SN002", "SN008"),

    # --- FMCG (3rd-Schedule goods) ------------------------------------
    ("Wholesaler",  "FMCG"):                 ("SN001", "SN002", "SN008", "SN027"),
    ("Distributor", "FMCG"):                 ("SN001", "SN002", "SN008", "SN027"),
    ("Manufacturer","FMCG"):                 ("SN001", "SN002", "SN008", "SN017"),

    # --- Pharmaceuticals ----------------------------------------------
    ("Manufacturer","Pharmaceuticals"):      ("SN001", "SN005", "SN006", "SN025"),
    ("Wholesaler",  "Pharmaceuticals"):      ("SN001", "SN005", "SN025"),

    # --- Mobile retailers / importers ---------------------------------
    ("Importer",    "Mobile"):               ("SN001", "SN015"),
    ("Retailer",    "Mobile"):               ("SN015", "SN026"),

    # --- Manufacturers ('All Other Sectors') --------------------------
    ("Manufacturer","All Other Sectors"):    ("SN001", "SN002", "SN016", "SN017"),

    # --- Importer / Exporter (general) --------------------------------
    ("Importer",    "All Other Sectors"):    ("SN001", "SN002", "SN007"),
    ("Exporter",    "All Other Sectors"):    ("SN001", "SN007"),

    # --- Service Providers --------------------------------------------
    # SN018 (FED-in-ST mode services) + SN019 (ICT Ordinance services).
    ("Service Provider", "Services"):        ("SN018", "SN019"),

    # --- Sector-specific industries -----------------------------------
    ("Manufacturer", "Steel"):               ("SN003", "SN004", "SN011"),
    ("Manufacturer", "Petroleum"):           ("SN012",),
    ("Manufacturer", "Cement or Concrete Blocks"): ("SN021",),
    ("Manufacturer", "Potassium Chlorate"):  ("SN022",),
    ("Manufacturer", "Electricity Distribution"): ("SN013",),
    ("Manufacturer", "Gas Distribution"):    ("SN014",),
    ("Manufacturer", "Telecom"):             ("SN010",),
    ("Manufacturer", "Automobile"):          ("SN020",),  # EV-specific
    ("Retailer",     "CNG Stations"):        ("SN023",),

    # --- Default fallback ---------------------------------------------
    ("*", "*"):                              ("SN001", "SN002"),
}


def _scenarios_for(nature: str, sector: str) -> set[str]:
    """Resolve the scenario codes for a single (nature, sector)
    using the lookup priority documented above."""
    for key in [
        (nature, sector),
        (nature, "*"),
        ("*", sector),
        ("*", "*"),
    ]:
        if key in ELIGIBLE_BY_NATURE_AND_SECTOR:
            return set(ELIGIBLE_BY_NATURE_AND_SECTOR[key])
    return set()


def assigned_scenario_codes(tenant: Tenant) -> list[str]:
    """The list of scenario CODES this tenant is required to pass.

    Resolution order:
      1. If tenant.assigned_scenarios is set (super-admin pasted the
         list from IRIS), use it verbatim. This is the source of truth.
      2. Otherwise fall back to our (nature × sector) best-guess table.

    Returned codes may include scenarios for which we have no builder
    (none currently — all SN001–SN028 are built — but a future FBR-added
    code could). Callers must use `builder_available()` to filter for
    runnable ones.
    """
    assigned = list(tenant.assigned_scenarios or [])
    if assigned:
        return sorted(set(assigned))

    # Fallback: the manual-derived nature×sector table.
    sector = tenant.fbr_sector or "All Other Sectors"
    natures = list(tenant.fbr_business_natures or [])
    if not natures:
        natures = ["*"]
    codes: set[str] = set()
    for nature in natures:
        codes |= _scenarios_for(nature, sector)
    return sorted(codes)


def pick_scenario_id(invoice, environment: str) -> str | None:
    """Choose the PRAL scenarioId for an invoice in sandbox (None in production).

    PRAL's scenarioId applies to the WHOLE invoice — every line's saleType must
    be compatible with it, and the scenario must be one the tenant is actually
    ASSIGNED, or PRAL rejects with errorCode 0204 ("Sale type not match with
    provided scenario"). This is the single source of truth for BOTH the submit
    task and the "Validate with FBR" action — keep them identical so a validate
    can never pass a scenario a submit would fail (or vice-versa).

    Selection (all-lines-of-a-kind → that scenario; mixed → standard):
      Exempt lines (saleType "Exempt goods"):   SN006 (6th Schedule)
      Zero-rate lines (saleType "Goods at zero-rate"): SN007 (5th Schedule)
      3rd-Schedule lines (fixedNotifiedValueOrRetailPrice > 0):
                            retail SN027  else SN008   (NEVER SN007 — that's
                            Zero-Rated 5th Schedule, a different thing entirely)
      Reduced-rate lines (8th Schedule):  retail SN028  else SN005
      Standard lines:       retail SN026  else (registered SN001 / walk-in SN002)

    Retail end-consumer scenarios (SN026/27/28) are only emitted for walk-in
    (unregistered) buyers AND only when assigned to the tenant. Exempt/zero pick
    SN006/SN007 only when assigned (their saleType is incompatible with any
    standard scenario, so a standard fallback would be rejected with 0204 — we'd
    rather send the correct code; if it isn't assigned the tenant must be granted
    it in FBR).
    """
    if environment != "sandbox":
        return None  # production classifies per-line via saleType; no scenarioId.

    assigned = set(assigned_scenario_codes(invoice.tenant))
    items = list(invoice.items.all())

    def _is_exempt(i):
        return (i.sale_type or "").strip().lower() == "exempt goods"

    def _is_zero_rate(i):
        return (i.sale_type or "").strip().lower() == "goods at zero-rate"

    def _is_third_schedule(i):
        return i.fixed_notified_value is not None and i.fixed_notified_value > 0

    def _is_reduced_rate(i):
        st = (i.sale_type or "")
        sro = (i.sro_schedule_no or "").upper()
        return "reduced rate" in st.lower() or "EIGHTH SCHEDULE" in sro

    def _is_services(i):
        # Services line: HS chapter 98, OR an explicit Services sale type.
        from .builder import is_services_hs_code
        st = (i.sale_type or "").strip().lower()
        return is_services_hs_code(i.hs_code) or st == "services"

    all_exempt = bool(items) and all(_is_exempt(i) for i in items)
    all_zero_rate = bool(items) and all(_is_zero_rate(i) for i in items)
    all_third_schedule = bool(items) and all(_is_third_schedule(i) for i in items)
    all_reduced_rate = bool(items) and all(_is_reduced_rate(i) for i in items)
    all_services = bool(items) and all(_is_services(i) for i in items)
    is_registered = (invoice.buyer_registration_type or "").lower() == "registered"

    def _pick(retail_code: str, fallback_code: str) -> str:
        # Retail end-consumer sales are unregistered by definition; only use the
        # retail scenario for walk-ins AND when it's in the tenant's set.
        if not is_registered and retail_code in assigned:
            return retail_code
        return fallback_code

    # Exempt / zero-rate first — their saleType matches ONLY SN006 / SN007, so
    # they can never use a standard/retail scenario. Prefer the correct code
    # when assigned; otherwise fall through (and PRAL will tell the operator the
    # scenario isn't assigned, which is the real problem to fix in FBR).
    if all_exempt and "SN006" in assigned:
        return "SN006"
    if all_zero_rate and "SN007" in assigned:
        return "SN007"
    if all_third_schedule:
        return _pick("SN027", "SN008")
    if all_reduced_rate:
        return _pick("SN028", "SN005")
    # Services (HS chapter 98 / saleType "Services") → SN019 ("Services (ICT
    # Ordinance)"). Confirmed against the sandbox validator for HS 9819.1300:
    # saleType "Services" + uoM "Others" + SN019 + a services-valid rate (16%)
    # validates; SN002/goods does not (0204/0099/0046).
    if all_services:
        return "SN019"
    if is_registered:
        return "SN001"
    return _pick("SN026", "SN002")


def eligible_scenarios(tenant: Tenant) -> list[ScenarioMeta]:
    """Scenarios this tenant must pass before production go-live AND
    for which we currently have a working payload-builder.

    Filters `assigned_scenario_codes(tenant)` through SCENARIOS so that
    codes IRIS assigned but we haven't built yet (e.g. SN026) are
    SILENTLY dropped from the runner's work list. The Tenant admin's
    UI surfaces the full assigned list separately, marking unbuilt
    scenarios as "Not yet supported" so the operator knows what's
    missing.
    """
    return [
        SCENARIOS[c] for c in assigned_scenario_codes(tenant)
        if c in SCENARIOS
    ]


# ---------------------------------------------------------------------------
# Helpers
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


# PRAL-canonical reference values, kept in one place so all builders
# stay in lockstep. Source of truth: GET /pdi/v1/{uom,itemdesccode}.
PRAL_UOM_PCS = "Numbers, pieces, units"
PRAL_UOM_KG = "KG"
PRAL_UOM_LTR = "Liter"

# A small set of PRAL-valid HS codes we lean on across scenarios.
# All verified to exist in /pdi/v1/itemdesccode.
PRAL_HS_RICE_OTHER = "1006.3090"
PRAL_HS_MOBILE_PHONE = "8517.1300"  # Most accurate phone HS code in PRAL list
PRAL_HS_SUGAR_CANE = "1701.1400"
PRAL_HS_PETROLEUM = "2710.1290"


def _test_registered_buyer_ntn(tenant: Tenant) -> tuple[str, str, str]:
    """Return (ntn, business_name, address) for a registered-buyer
    scenario test (SN001, SN005, etc.).

    Reads `Tenant.fbr_test_buyer_ntn` — the operator pastes the NTN of
    a real partner business that PRAL has on file. Without that,
    registered-buyer scenarios always fail because PRAL's documented
    test NTN "1000000000007" is not actually registered in their
    sandbox database (PralSandboxQuirks #4).

    Falls back to "1000000000007" so the test still *runs* and produces
    PRAL's clear "Provided scenario not valid for unregistered user"
    error — which itself signals to the operator that they need to set
    a real NTN.
    """
    override = (tenant.fbr_test_buyer_ntn or "").strip()
    if override:
        return (override, "Test Registered Buyer", "Lahore")
    return ("1000000000007", "Test Registered Buyer", "Test buyer address")




# ============================================================================
# CANONICAL 28-SCENARIO BUILDER REGISTRY
# ============================================================================
#
# Below: one @register decorator + builder function per FBR scenarioId.
# Each builder produces a complete PRAL payload matching the exact
# saleType / sroScheduleNo / sroItemSerialNo / extraTax / rate spec
# documented in the eyeconconsultant scenario testing guide.
#
# Conventions:
#   - All builders start from `_base_payload()` which returns the
#     common header + a single seed item. Each scenario then mutates
#     `payload["items"][0]` to set its specific fields. Multi-item
#     scenarios override `payload["items"]` entirely.
#   - `_test_registered_buyer_ntn(tenant)` returns a real partner NTN
#     when set, else the docs default (which fails predictably).
#   - `_invoice_ref(code, tenant)` produces a unique invoiceRefNo so
#     PRAL doesn't reject duplicates with errorCode 0026.
#   - Money values are floats with at most 2 decimal places (PRAL's
#     errorCode 0302 rule).


# ---------------------------------------------------------------------------
# Common helpers used by all 28 builders
# ---------------------------------------------------------------------------


def _invoice_ref(code: str, tenant: Tenant) -> str:
    """Synthetic invoice reference that won't collide with real sales."""
    return f"SCEN-{code}-{tenant.id.hex[:8]}"


def _walk_in_buyer() -> dict:
    """Buyer block for unregistered walk-in scenarios."""
    return {
        "buyerNTNCNIC": "0000000000000",
        "buyerBusinessName": "Walk-in Customer",
        "buyerAddress": "",
        "buyerRegistrationType": "Unregistered",
    }


def _registered_buyer(tenant: Tenant) -> dict:
    """Buyer block for registered scenarios — uses the tenant-supplied
    partner NTN, with a clear fallback if none configured."""
    ntn, name, addr = _test_registered_buyer_ntn(tenant)
    return {
        "buyerNTNCNIC": ntn,
        "buyerBusinessName": name,
        "buyerAddress": addr,
        "buyerRegistrationType": "Registered",
    }


def _base_payload(tenant: Tenant, code: str, *, registered: bool) -> dict:
    """Common envelope. Caller then customises `items[0]`."""
    buyer = _registered_buyer(tenant) if registered else _walk_in_buyer()
    return {
        "invoiceType": "Sale Invoice",
        "invoiceDate": _today(),
        **_seller_block(tenant),
        **buyer,
        "buyerProvince": tenant.province,
        "invoiceRefNo": _invoice_ref(code, tenant),
        "scenarioId": code,
        "items": [_default_item()],
    }


def _default_item() -> dict:
    """A baseline single-item line. Each scenario overrides what it
    needs. Defaults are picked to be NEUTRAL — extraTax="" so it
    survives reduced-rate scenarios, 0% withholding, no SRO."""
    return {
        "hsCode": PRAL_HS_RICE_OTHER,
        "productDescription": "Rice (sandbox test item)",
        "rate": "18%",
        "uoM": PRAL_UOM_KG,
        "quantity": 5,
        "totalValues": 1180.00,
        "valueSalesExcludingST": 1000.00,
        "fixedNotifiedValueOrRetailPrice": 0,
        "salesTaxApplicable": 180.00,
        "salesTaxWithheldAtSource": 0,
        "extraTax": "",  # PRAL spec: empty string, not 0
        "furtherTax": 0,
        "sroScheduleNo": "",
        "sroItemSerialNo": "",
        "fedPayable": 0,
        "discount": 0,
        "saleType": "Goods at standard rate (default)",
    }


# ===========================================================================
# SN001 — Standard Rate Goods to Registered Buyers
# ===========================================================================


@register(
    "SN001",
    description="Standard Rate Goods to Registered Buyers",
    sectors=("All Other Sectors", "FMCG", "Pharmaceuticals", "Mobile",
             "Wholesale / Retails"),
    needs_registered_buyer=True,
)
def build_sn001(tenant: Tenant) -> dict:
    """18% standard rate, B2B (registered buyer). Input-tax-credit eligible."""
    return _base_payload(tenant, "SN001", registered=True)


# ===========================================================================
# SN002 — Standard Rate Goods to Unregistered Buyers
# ===========================================================================


@register(
    "SN002",
    description="Standard Rate Goods to Unregistered Buyers",
    sectors=("All Other Sectors", "FMCG", "Wholesale / Retails"),
)
def build_sn002(tenant: Tenant) -> dict:
    """18% standard rate, walk-in / unregistered buyer (B2C)."""
    return _base_payload(tenant, "SN002", registered=False)


# ===========================================================================
# SN003 — Steel (Melted / Re-Rolled)
# ===========================================================================


@register(
    "SN003",
    description="Steel (Melted / Re-Rolled)",
    sectors=("Steel",),
)
def build_sn003(tenant: Tenant) -> dict:
    """Re-rolled steel sale, 18% standard rate, special saleType.
    HS code per guide: 7214.1010."""
    p = _base_payload(tenant, "SN003", registered=False)
    p["items"][0].update({
        "hsCode": "7214.1010",
        "productDescription": "Steel bars (re-rolled)",
        "uoM": "MT",
        "quantity": 1,
        "totalValues": 118000.00,
        "valueSalesExcludingST": 100000.00,
        "salesTaxApplicable": 18000.00,
        "saleType": "Steel melting and re-rolling",
    })
    return p


# ===========================================================================
# SN004 — Steel Scrap by Ship Breakers
# ===========================================================================


@register(
    "SN004",
    description="Steel Scrap by Ship Breakers",
    sectors=("Steel",),
)
def build_sn004(tenant: Tenant) -> dict:
    """Ship-breaking scrap sale. HS code per guide: 7204.1010."""
    p = _base_payload(tenant, "SN004", registered=False)
    p["items"][0].update({
        "hsCode": "7204.1010",
        "productDescription": "Steel scrap (ship-breaking)",
        "uoM": "MT",
        "quantity": 2,
        "totalValues": 236000.00,
        "valueSalesExcludingST": 200000.00,
        "salesTaxApplicable": 36000.00,
        "saleType": "Ship breaking",
    })
    return p


# ===========================================================================
# SN005 — Reduced Rate Goods (8th Schedule)
# ===========================================================================


@register(
    "SN005",
    description="Reduced Rate Goods (8th Schedule)",
    sectors=("All Other Sectors", "Pharmaceuticals"),
)
def build_sn005(tenant: Tenant) -> dict:
    """1% reduced rate per 8th Schedule. extraTax MUST be empty string
    (sending 0 trips errorCode 0091)."""
    p = _base_payload(tenant, "SN005", registered=False)
    p["items"][0].update({
        "rate": "1%",
        "totalValues": 1010.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 10.00,
        "extraTax": "",  # critical
        # PRAL expects this exact casing — verified via eyeconconsultant
        # guide and PRAL error 0028 ("Valid SRO/Schedule No. is mandatory
        # where rate is not 18%"). Strings like "8TH SCHEDULE" or
        # "EIGHTH SCHEDULE TABLE I" (roman) are rejected.
        "sroScheduleNo": "EIGHTH SCHEDULE Table 1",
        "sroItemSerialNo": "82",
        "saleType": "Goods at Reduced Rate",
    })
    return p


# ===========================================================================
# SN006 — Exempt Goods (6th Schedule)
# ===========================================================================


@register(
    "SN006",
    description="Exempt Goods (6th Schedule)",
    sectors=("All Other Sectors", "Pharmaceuticals"),
)
def build_sn006(tenant: Tenant) -> dict:
    """Tax-exempt goods per 6th Schedule. rate="Exempt", tax=0."""
    p = _base_payload(tenant, "SN006", registered=True)
    p["items"][0].update({
        "rate": "Exempt",
        "totalValues": 1000.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 0,
        "sroScheduleNo": "6th Schd Table I",
        "saleType": "Exempt goods",
    })
    return p


# ===========================================================================
# SN007 — Zero-Rated Goods (5th Schedule)
# ===========================================================================


@register(
    "SN007",
    description="Zero-Rated Goods (5th Schedule)",
    sectors=("All Other Sectors", "Pharmaceuticals"),
)
def build_sn007(tenant: Tenant) -> dict:
    """0% zero-rated supply per 5th Schedule."""
    p = _base_payload(tenant, "SN007", registered=False)
    p["items"][0].update({
        "rate": "0%",
        "totalValues": 1000.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 0,
        "sroScheduleNo": "327(I)/2008",
        "saleType": "Goods at zero-rate",
    })
    return p


# ===========================================================================
# SN008 — 3rd Schedule Goods
# ===========================================================================


@register(
    "SN008",
    description="3rd Schedule Goods",
    sectors=("All Other Sectors", "FMCG", "Wholesale / Retails"),
)
def build_sn008(tenant: Tenant) -> dict:
    """3rd-Schedule goods (sugar / drinks / biscuits / cigarettes).
    Tax computed on retail price, NOT on the actual sale value.

    PRAL rule for 3rd Schedule (settled after 3 sandbox iterations):
      - salesTaxApplicable     = retail * rate / 100   (tax computed ON retail)
      - valueSalesExcludingST  = retail                (must be non-zero;
                                                         PRAL rejects 0 as
                                                         "must not be empty")
      - totalValues            = retail + salesTaxApplicable

    Earlier attempts:
      - tax=retail*rate/118 → "tax doesn't match calculated" (0102)
      - valueExcl=0         → "must not be negative, null, empty" (0302-ish)

    The third interpretation (this one) treats `valueExcl` as a
    *required positive number* + computes tax fresh from retail. Both
    the rate-based math AND the field-non-empty rule are satisfied.
    """
    p = _base_payload(tenant, "SN008", registered=False)
    retail = 1180.00
    rate_pct = 18
    tax = round(retail * rate_pct / 100, 2)
    p["items"][0].update({
        "hsCode": "1701.9910",  # refined cane sugar — canonical 3rd-Sched item
        "productDescription": "Sugar (3rd Schedule)",
        "uoM": "KG",
        "quantity": 4,
        "totalValues": retail + tax,
        "valueSalesExcludingST": retail,
        "fixedNotifiedValueOrRetailPrice": retail,
        "salesTaxApplicable": tax,
        "saleType": "3rd Schedule Goods",
    })
    return p


# ===========================================================================
# SN009 — Purchase from Cotton Ginners
# ===========================================================================


@register(
    "SN009",
    description="Purchase from Cotton Ginners",
    sectors=("All Other Sectors",),
    needs_registered_buyer=True,
)
def build_sn009(tenant: Tenant) -> dict:
    """Cotton ginner sales — sector-specific. 18% standard rate."""
    p = _base_payload(tenant, "SN009", registered=True)
    p["items"][0].update({
        "hsCode": "5201.0000",
        "productDescription": "Raw cotton (ginned)",
        "uoM": "KG",
        "quantity": 100,
        "totalValues": 1180.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 180.00,
        "saleType": "Cotton ginners",
    })
    return p


# ===========================================================================
# SN010 — Telecom Services by Mobile Operators
# ===========================================================================


@register(
    "SN010",
    description="Telecom Services by Mobile Operators",
    sectors=("Telecom",),
)
def build_sn010(tenant: Tenant) -> dict:
    """Telecom services, 17% rate (services-side rate; not 18%).
    PRAL still requires hsCode for services — use a placeholder."""
    p = _base_payload(tenant, "SN010", registered=False)
    p["items"][0].update({
        "hsCode": "9803.0000",  # telecom services placeholder
        "productDescription": "Mobile telephony service (postpaid)",
        "uoM": PRAL_UOM_PCS,
        "rate": "17%",
        "quantity": 1,
        "totalValues": 1170.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 170.00,
        "saleType": "Telecommunication services",
    })
    return p


# ===========================================================================
# SN011 — Steel via Toll Manufacturing
# ===========================================================================


@register(
    "SN011",
    description="Steel via Toll Manufacturing",
    sectors=("Steel",),
)
def build_sn011(tenant: Tenant) -> dict:
    """Toll-manufacturing steel processing. HS per guide: 7214.9990."""
    p = _base_payload(tenant, "SN011", registered=False)
    p["items"][0].update({
        "hsCode": "7214.9990",
        "productDescription": "Steel (toll manufactured)",
        "uoM": "MT",
        "quantity": 1,
        "totalValues": 118000.00,
        "valueSalesExcludingST": 100000.00,
        "salesTaxApplicable": 18000.00,
        "saleType": "Toll Manufacturing",
    })
    return p


# ===========================================================================
# SN012 — Petroleum Products
# ===========================================================================


@register(
    "SN012",
    description="Petroleum Products",
    sectors=("Petroleum",),
)
def build_sn012(tenant: Tenant) -> dict:
    """Petroleum products at 1.43% per SRO 1450(I)/2021."""
    p = _base_payload(tenant, "SN012", registered=False)
    p["items"][0].update({
        "hsCode": PRAL_HS_PETROLEUM,  # 2710.1290
        "productDescription": "Petroleum product (HSD)",
        "uoM": PRAL_UOM_LTR,
        "rate": "1.43%",
        "quantity": 1000,
        "totalValues": 1014.30,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 14.30,
        "sroScheduleNo": "1450(I)/2021",
        "saleType": "Petroleum Products",
    })
    return p


# ===========================================================================
# SN013 — Electricity to Retailers
# ===========================================================================


@register(
    "SN013",
    description="Electricity Supply to Retailers",
    sectors=("Electricity Distribution",),
)
def build_sn013(tenant: Tenant) -> dict:
    """Electricity supply to retail end. 5% rate."""
    p = _base_payload(tenant, "SN013", registered=False)
    p["items"][0].update({
        "hsCode": "2716.0000",  # Electrical energy
        "productDescription": "Electricity supply (commercial)",
        "uoM": PRAL_UOM_PCS,
        "rate": "5%",
        "quantity": 1,
        "totalValues": 1050.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 50.00,
        "saleType": "Electricity Supply to Retailers",
    })
    return p


# ===========================================================================
# SN014 — Gas to CNG Stations
# ===========================================================================


@register(
    "SN014",
    description="Gas to CNG Stations",
    sectors=("Gas Distribution",),
)
def build_sn014(tenant: Tenant) -> dict:
    """Gas supplied to CNG fuel stations. 18%."""
    p = _base_payload(tenant, "SN014", registered=False)
    p["items"][0].update({
        "hsCode": "2711.2100",  # Natural gas, gaseous
        "productDescription": "Natural gas supply to CNG station",
        "uoM": "Cubic Metre",
        "quantity": 1000,
        "totalValues": 1180.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 180.00,
        "saleType": "Gas to CNG stations",
    })
    return p


# ===========================================================================
# SN015 — Mobile Phones (Ninth Schedule)
# ===========================================================================


@register(
    "SN015",
    description="Mobile Phones (9th Schedule)",
    sectors=("Mobile",),
)
def build_sn015(tenant: Tenant) -> dict:
    """Mobile phone — 9th-Schedule fixed retail price.
    Guide says sroScheduleNo="NINTH SCHEDULE", sroItemSerialNo="1(A)"."""
    p = _base_payload(tenant, "SN015", registered=False)
    p["items"][0] = {
        "hsCode": PRAL_HS_MOBILE_PHONE,
        "productDescription": "Mobile phone",
        "rate": "18%",
        "uoM": PRAL_UOM_PCS,
        "quantity": 1,
        "totalValues": 35400.00,
        "valueSalesExcludingST": 30000.00,
        "fixedNotifiedValueOrRetailPrice": 35400.00,
        "salesTaxApplicable": 5400.00,
        "salesTaxWithheldAtSource": 0,
        "extraTax": "",
        "furtherTax": 0,
        "sroScheduleNo": "NINTH SCHEDULE",
        "sroItemSerialNo": "1(A)",
        "fedPayable": 0,
        "discount": 0,
        "saleType": "Mobile Phones",
    }
    return p


# ===========================================================================
# SN016 — Processing / Conversion of Goods
# ===========================================================================


@register(
    "SN016",
    description="Processing / Conversion of Goods",
    sectors=("All Other Sectors",),
)
def build_sn016(tenant: Tenant) -> dict:
    """Value-added processing service. 5% rate."""
    p = _base_payload(tenant, "SN016", registered=False)
    p["items"][0].update({
        "rate": "5%",
        "totalValues": 1050.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 50.00,
        "saleType": "Processing/Conversion of Goods",
    })
    return p


# ===========================================================================
# SN017 — Goods (FED in ST Mode)
# ===========================================================================


@register(
    "SN017",
    description="Goods (FED in ST Mode)",
    sectors=("All Other Sectors", "FMCG"),
)
def build_sn017(tenant: Tenant) -> dict:
    """Federal Excise applied through the Sales Tax channel. 8%."""
    p = _base_payload(tenant, "SN017", registered=False)
    p["items"][0].update({
        "rate": "8%",
        "totalValues": 1080.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 80.00,
        "saleType": "Goods (FED in ST Mode)",
    })
    return p


# ===========================================================================
# SN018 — Services (FED in ST Mode)
# ===========================================================================


@register(
    "SN018",
    description="Services (FED in ST Mode)",
    sectors=("Services",),
)
def build_sn018(tenant: Tenant) -> dict:
    """Insurance / advertising / franchise services billed via ST mode."""
    p = _base_payload(tenant, "SN018", registered=False)
    p["items"][0].update({
        "hsCode": "9805.0000",  # Insurance services placeholder
        "productDescription": "Insurance service (FED in ST mode)",
        "uoM": PRAL_UOM_PCS,
        "rate": "8%",
        "quantity": 1,
        "totalValues": 1080.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 80.00,
        "saleType": "Services (FED in ST Mode)",
    })
    return p


# ===========================================================================
# SN019 — Services (ICT Ordinance)
# ===========================================================================


@register(
    "SN019",
    description="Services (ICT Ordinance)",
    sectors=("Services",),
)
def build_sn019(tenant: Tenant) -> dict:
    """ICT-Ordinance services. 5% per ICTO Table I."""
    p = _base_payload(tenant, "SN019", registered=False)
    p["items"][0].update({
        "hsCode": "9801.0000",
        "productDescription": "ICT service",
        "uoM": PRAL_UOM_PCS,
        "rate": "5%",
        "quantity": 1,
        "totalValues": 1050.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 50.00,
        "sroScheduleNo": "ICTO TABLE I",
        "sroItemSerialNo": "1(ii)(ii)(a)",
        "saleType": "Services",
    })
    return p


# ===========================================================================
# SN020 — Electric Vehicles
# ===========================================================================


@register(
    "SN020",
    description="Electric Vehicles",
    sectors=("Automobile",),
)
def build_sn020(tenant: Tenant) -> dict:
    """EVs — 1% concessional rate per 6th Schedule Table III item 20."""
    p = _base_payload(tenant, "SN020", registered=False)
    p["items"][0].update({
        "hsCode": "8703.8000",
        "productDescription": "Electric vehicle (passenger)",
        "uoM": PRAL_UOM_PCS,
        "rate": "1%",
        "quantity": 1,
        "totalValues": 4040000.00,
        "valueSalesExcludingST": 4000000.00,
        "salesTaxApplicable": 40000.00,
        "extraTax": "",
        "sroScheduleNo": "6th Schd Table III",
        "sroItemSerialNo": "20",
        "saleType": "Electric Vehicle",
    })
    return p


# ===========================================================================
# SN021 — Cement / Concrete Block (per-unit fixed tax)
# ===========================================================================


@register(
    "SN021",
    description="Cement / Concrete Block",
    sectors=("Cement or Concrete Blocks",),
)
def build_sn021(tenant: Tenant) -> dict:
    """Cement / concrete blocks at Rs.3 per unit fixed tax."""
    p = _base_payload(tenant, "SN021", registered=False)
    qty = 1000
    fixed_tax_per_unit = 3
    p["items"][0].update({
        "hsCode": "6810.1100",
        "productDescription": "Concrete block",
        "uoM": PRAL_UOM_PCS,
        "rate": "Rs.3 per unit",
        "quantity": qty,
        "totalValues": qty * 25.00 + qty * fixed_tax_per_unit,  # 25 unit price + 3 fixed
        "valueSalesExcludingST": qty * 25.00,
        "fixedNotifiedValueOrRetailPrice": fixed_tax_per_unit,
        "salesTaxApplicable": qty * fixed_tax_per_unit,
        "saleType": "Cement /Concrete Block",
    })
    return p


# ===========================================================================
# SN022 — Potassium Chlorate
# ===========================================================================


@register(
    "SN022",
    description="Potassium Chlorate",
    sectors=("Potassium Chlorate",),
)
def build_sn022(tenant: Tenant) -> dict:
    """Dual-rate item: 18% + Rs.60/kg fixed."""
    p = _base_payload(tenant, "SN022", registered=False)
    qty = 100
    p["items"][0].update({
        "hsCode": "2829.1900",
        "productDescription": "Potassium chlorate",
        "uoM": "KG",
        "rate": "18% + Rs.60/kg",
        "quantity": qty,
        "totalValues": 1180.00 + (qty * 60),
        "valueSalesExcludingST": 1000.00,
        "fixedNotifiedValueOrRetailPrice": 60,
        "salesTaxApplicable": 180.00 + (qty * 60),  # both rates apply
        "saleType": "Potassium Chlorate",
    })
    return p


# ===========================================================================
# SN023 — CNG Sales
# ===========================================================================


@register(
    "SN023",
    description="CNG Sales",
    sectors=("CNG Stations",),
)
def build_sn023(tenant: Tenant) -> dict:
    """CNG fuel sales at fixed Rs.200/unit per SRO 581(1)/2024 Region-I."""
    p = _base_payload(tenant, "SN023", registered=False)
    qty = 10
    p["items"][0].update({
        "hsCode": "2711.2100",
        "productDescription": "CNG fuel",
        "uoM": "Cubic Metre",
        "rate": "Rs.200/unit",
        "quantity": qty,
        "totalValues": qty * 250.00,
        "valueSalesExcludingST": qty * 50.00,
        "fixedNotifiedValueOrRetailPrice": 200,
        "salesTaxApplicable": qty * 200,
        "sroScheduleNo": "581(1)/2024",
        "sroItemSerialNo": "Region-I",
        "saleType": "CNG Sales",
    })
    return p


# ===========================================================================
# SN024 — Goods per SRO 297(I)/2023 (uses PIPE | not letter I in saleType)
# ===========================================================================


@register(
    "SN024",
    description="Goods per SRO 297(I)/2023",
    sectors=("All Other Sectors",),
)
def build_sn024(tenant: Tenant) -> dict:
    """25% special-rate goods. Critical: saleType uses pipe character |,
    NOT letter I. PRAL is strict — typo trips errorCode 0204."""
    p = _base_payload(tenant, "SN024", registered=False)
    p["items"][0].update({
        "rate": "25%",
        "totalValues": 1250.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 250.00,
        "sroScheduleNo": "297(I)/2023-Table-I",
        "saleType": "Goods as per SRO.297(|)/2023",  # PIPE not LETTER I
    })
    return p


# ===========================================================================
# SN025 — Drugs (8th Schedule Serial 81)
# ===========================================================================


@register(
    "SN025",
    description="Drugs (8th Schedule Serial 81)",
    sectors=("Pharmaceuticals",),
)
def build_sn025(tenant: Tenant) -> dict:
    """Pharmaceutical drug at 0% per 8th Schedule Serial 81 — non-adjustable."""
    p = _base_payload(tenant, "SN025", registered=False)
    p["items"][0].update({
        "hsCode": "3004.9099",
        "productDescription": "Medicine (drug)",
        "uoM": PRAL_UOM_PCS,
        "rate": "0%",
        "totalValues": 1000.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 0,
        # Same exact-casing rule as SN005/SN028.
        "sroScheduleNo": "EIGHTH SCHEDULE Table 1",
        "sroItemSerialNo": "81",
        "saleType": "Non-Adjustable Supplies",
    })
    return p


# ===========================================================================
# SN026 — Standard Rate to End Consumers (Retailers)
# ===========================================================================


@register(
    "SN026",
    description="Standard Rate to End Consumers (Retailers)",
    sectors=("All Other Sectors", "Wholesale / Retails", "FMCG"),
)
def build_sn026(tenant: Tenant) -> dict:
    """Retail-flow scenario — sale to an END CONSUMER (walk-in shopper).
    "End consumer" in PK tax law = unregistered buyer, not B2B.

    Resolved after sandbox iteration: the eyeconconsultant guide
    column labelled SN026 as 'Registered', but PRAL's runtime check
    rejects that with "Registration type does not match Buyer's
    profile" — the registered-buyer table in sandbox doesn't accept
    any NTN we have access to. The actual rule: walk-in / unregistered
    buyer (NTN = 0000000000000), same as SN002 but with the retail-
    flow scenarioId.
    """
    p = _base_payload(tenant, "SN026", registered=False)
    # Same shape as SN002 (standard rate 18%, walk-in), but PRAL
    # routes it through retailer-end-consumer reporting rules via
    # the scenarioId.
    return p


# ===========================================================================
# SN027 — 3rd Schedule to End Consumers (Retailers)
# ===========================================================================


@register(
    "SN027",
    description="3rd Schedule to End Consumers (Retailers)",
    sectors=("All Other Sectors", "Wholesale / Retails", "FMCG"),
)
def build_sn027(tenant: Tenant) -> dict:
    """Retail-flow 3rd-Schedule sale to an end consumer (walk-in).
    UNregistered buyer (see SN026 for why); 3rd-Schedule math from
    SN008 (retail-price = valueExcl = fixedNotified; tax = retail × 18%
    computed ON retail)."""
    p = _base_payload(tenant, "SN027", registered=False)
    retail = 1180.00
    rate_pct = 18
    tax = round(retail * rate_pct / 100, 2)
    p["items"][0].update({
        "hsCode": "1701.9910",
        "productDescription": "Sugar (retail-end 3rd Schedule)",
        "uoM": "KG",
        "quantity": 4,
        "totalValues": retail + tax,
        "valueSalesExcludingST": retail,
        "fixedNotifiedValueOrRetailPrice": retail,
        "salesTaxApplicable": tax,
        "saleType": "3rd Schedule Goods",
    })
    return p


# ===========================================================================
# SN028 — Reduced Rate to End Consumers (Retailers)
# ===========================================================================


@register(
    "SN028",
    description="Reduced Rate to End Consumers (Retailers)",
    sectors=("All Other Sectors", "Wholesale / Retails", "FMCG"),
)
def build_sn028(tenant: Tenant) -> dict:
    """Retail-flow reduced-rate sale to end consumer (walk-in).
    UNregistered buyer (see SN026 reasoning); 1% rate; extraTax=""
    (critical — sending 0 trips errorCode 0091).

    SRO casing matters: PRAL expects "EIGHTH SCHEDULE Table 1"
    (exact case + arabic digit 1). Variants "8TH SCHEDULE" and
    "EIGHTH SCHEDULE TABLE I" are both rejected with errorCode 0028.
    """
    p = _base_payload(tenant, "SN028", registered=False)
    p["items"][0].update({
        "rate": "1%",
        "totalValues": 1010.00,
        "valueSalesExcludingST": 1000.00,
        "salesTaxApplicable": 10.00,
        "extraTax": "",  # critical
        "sroScheduleNo": "EIGHTH SCHEDULE Table 1",
        "sroItemSerialNo": "70",
        "saleType": "Goods at Reduced Rate",
    })
    return p
