"""Business-mode + FBR taxonomy.

Three concepts live here:

1. **Business mode** — what kind of product this tenant runs:
     - 'pos'                 a counter-side POS with cashiers, drawer, etc.
     - 'digital_invoicing'   a back-office invoice tool, no till
     - 'both'                same tenant uses both surfaces
   Stored on `Tenant.business_mode`. Used at onboarding to flip the
   right set of modules ON (POS gets terminals + hardware + customer
   display; DI gets none of those).

2. **FBR Business Nature** — the PRAL-defined taxonomy of "what role
   does this business play in the supply chain". Wire values are exact
   strings PRAL accepts; we expose them as choices on the Tenant model
   so the admin + onboarding wizard render a dropdown, not free text.
   Wrong nature => FBR rejects the invoice with a cryptic error.

3. **FBR Sector** — the PRAL-defined industry list. Same rules as
   nature: exact wire values, expose as choices, single-select per
   tenant. The list of eligible scenarioIds is derived from
   (nature, sector) in apps/fbr/scenarios.py.

Keep this module dependency-free (no Django imports) so it can be
referenced from migrations + tests without circular imports.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Business mode
# ---------------------------------------------------------------------------

BUSINESS_MODES = (
    (
        "pos",
        "POS — counter-side terminal",
    ),
    (
        "digital_invoicing",
        "Digital Invoicing only — back-office",
    ),
    (
        "both",
        "Both POS and Digital Invoicing",
    ),
)

DEFAULT_BUSINESS_MODE = "digital_invoicing"


# ---------------------------------------------------------------------------
# FBR connection type — HOW the tenant reaches FBR (orthogonal to business_mode,
# which is WHICH product they bought).
#
#   di_api  — direct PRAL Digital Invoicing API: tenant holds a Bearer token,
#             tests sandbox scenarios, then submits straight to gw.fbr.gov.pk.
#             Needs: token setup, sandbox/production tokens, scenario testing.
#   ims_sdc — FBR's IMS Fiscalization service (SDC) runs on the shop machine and
#             relays to FBR. Our server sends the POS ID to localhost:8524; NO
#             Bearer token is used on this path, and there are NO sandbox
#             scenarios (the IMS handles activation itself).
#
# This flag drives mode-aware UI: ims_sdc tenants must NOT see DI-API token
# setup or scenarios; di_api tenants must NOT see POS-ID-only / SDC controls.
# ---------------------------------------------------------------------------

FBR_CONNECTION_TYPES = (
    ("di_api", "Direct DI-API (PRAL Bearer token + scenarios)"),
    ("ims_sdc", "IMS / SDC Fiscalization service (POS ID, no token, no scenarios)"),
)

DEFAULT_FBR_CONNECTION_TYPE = "di_api"


# ---------------------------------------------------------------------------
# Vertical — WHAT KIND of shop this is (grocery vs pharmacy vs …).
#
# Orthogonal to business_mode (which surface) and fbr_connection_type (how it
# reaches FBR). The vertical is a *presentation* flag only: it decides which
# UI sections each app surfaces (a pharmacy sees batch/expiry/supplier tools; a
# grocery does not). It does NOT change what the backend allows — access stays
# governed by `modules_enabled`. Existing tenants default to 'grocery', so
# nothing changes for them.
#
# Restaurant is intentionally deferred (V2); adding it later is one more enum
# entry plus the vertical-gated screens.
# ---------------------------------------------------------------------------

VERTICALS = (
    ("grocery", "Grocery / general retail"),
    ("pharmacy", "Pharmacy"),
)

DEFAULT_VERTICAL = "grocery"


# Which modules each mode unlocks. Used by the onboarding wizard +
# whenever business_mode flips. Forced modules (sales/fbr/customers)
# are always on regardless and are not listed here.
#
# Rationale:
# - POS: needs branches, terminals, inventory, hardware, customer
#   display, payments_advanced, returns. Reports + audit are useful
#   too. Most modules on.
# - Digital Invoicing: no till, no hardware. Just sales + fbr +
#   customers + (optionally) debit/credit notes + manual amendments
#   + basic reports + audit. Inventory is opt-in — a wholesaler may
#   want stock tracking, a service provider doesn't.
# - Both: every module on; super-admin can trim later.
DEFAULT_MODULES_FOR_MODE: dict[str, list[str]] = {
    "pos": [
        "sales", "fbr", "customers",
        "branches", "terminals", "inventory", "returns",
        "debit_credit_notes", "manual_amendments",
        "payments_advanced", "customer_display", "hardware",
        "reports_basic", "reports_advanced", "audit_log",
    ],
    "digital_invoicing": [
        "sales", "fbr", "customers",
        "debit_credit_notes", "manual_amendments",
        "reports_basic", "audit_log",
    ],
    "both": [
        "sales", "fbr", "customers",
        "branches", "terminals", "inventory", "returns",
        "debit_credit_notes", "manual_amendments",
        "payments_advanced", "customer_display", "hardware",
        "reports_basic", "reports_advanced", "audit_log",
    ],
}


def default_modules_for_mode(mode: str) -> list[str]:
    """Return the module-key list a tenant in `mode` should start with.
    Falls back to digital_invoicing's minimal set if `mode` is unknown."""
    return list(DEFAULT_MODULES_FOR_MODE.get(mode, DEFAULT_MODULES_FOR_MODE["digital_invoicing"]))


# ---------------------------------------------------------------------------
# FBR Business Nature
# ---------------------------------------------------------------------------
#
# Exact strings PRAL accepts. The DI manual v1.6 shows these as checkboxes;
# a tenant can pick multiple (e.g. a business that imports AND wholesales).
# We expose them as a multi-select on the Tenant model via
# fbr_business_natures = ArrayField(choices=FBR_BUSINESS_NATURE_CHOICES).

FBR_BUSINESS_NATURES = (
    "Manufacturer",
    "Importer",
    "Exporter",
    "Distributor",
    "Wholesaler",
    "Retailer",
    "Service Provider",
    "Other",
)

FBR_BUSINESS_NATURE_CHOICES = tuple((v, v) for v in FBR_BUSINESS_NATURES)


# ---------------------------------------------------------------------------
# FBR Sector
# ---------------------------------------------------------------------------
#
# Single-select per tenant (the manual UI is radio buttons).
# Some are very industry-specific (Potassium Chlorate is a controlled
# precursor; CNG Stations is a regulated retail vertical) — we don't
# pre-judge which is appropriate. "All Other Sectors" is the safe
# fallback for businesses that don't map cleanly.

FBR_SECTORS = (
    "Potassium Chlorate",
    "Cement or Concrete Blocks",
    "Mobile",
    "Wholesale / Retails",
    "Pharmaceuticals",
    "CNG Stations",
    "Automobile",
    "Services",
    "Gas Distribution",
    "Electricity Distribution",
    "Petroleum",
    "Telecom",
    "Textile",
    "FMCG",
    "Steel",
    "All Other Sectors",
)

FBR_SECTOR_CHOICES = tuple((v, v) for v in FBR_SECTORS)


# ---------------------------------------------------------------------------
# Nature → likely default sector. Used to pre-fill the onboarding
# wizard so the operator doesn't stare at a blank dropdown.
# Operators can always change it. These are educated guesses, not
# compliance rules.
# ---------------------------------------------------------------------------

LIKELY_SECTOR_FOR_NATURE: dict[str, str] = {
    "Manufacturer": "All Other Sectors",
    "Importer": "All Other Sectors",
    "Exporter": "All Other Sectors",
    "Distributor": "Wholesale / Retails",
    "Wholesaler": "Wholesale / Retails",
    "Retailer": "Wholesale / Retails",
    "Service Provider": "Services",
    "Other": "All Other Sectors",
}
