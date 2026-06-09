"""Per-tenant module catalog.

The super-admin checks off which modules each tenant is allowed to use
when creating or editing the tenant. Modules are coarser than role
permissions (which gate per-USER actions inside an enabled module) and
distinct from subscription-plan limits (which cap quantities like
max_terminals). They answer the question:

    "Should this tenant see Inventory at all?"

Forced modules cannot be disabled — they are the product itself.
Everything else is opt-in per-tenant.

The catalog is the authoritative source; do not hard-code module keys
elsewhere — import MODULE_KEYS or use is_module_enabled().
"""

from __future__ import annotations

from typing import TypedDict


class _Module(TypedDict):
    key: str
    label: str
    group: str
    description: str
    forced: bool


# Listed in the order they should appear in the super-admin checklist.
# Group headers come from the `group` field; render in this order:
#   "Sales & FBR"  →  "Multi-location"  →  "Operations"  →  "Insights"
MODULES: list[_Module] = [
    # --- Sales & FBR (the product itself) ---
    {
        "key": "sales",
        "label": "Invoices",
        "group": "Sales & FBR",
        "description": "Create, list, and manage invoices. Cannot be "
                       "disabled — this is the core product.",
        "forced": True,
    },
    {
        "key": "fbr",
        "label": "FBR Digital Invoicing",
        "group": "Sales & FBR",
        "description": "Submit invoices to PRAL and store FBR tokens. "
                       "Cannot be disabled — FBR submission is the "
                       "primary value of the platform.",
        "forced": True,
    },
    {
        "key": "customers",
        "label": "Customers",
        "group": "Sales & FBR",
        "description": "Customer database with NTN/CNIC. Cannot be "
                       "disabled — FBR registered-buyer scenarios "
                       "require a customer record with NTN, so the "
                       "platform always needs this surface.",
        "forced": True,
    },
    # --- Multi-location ---
    {
        "key": "branches",
        "label": "Multi-branch",
        "group": "Multi-location",
        "description": "Multiple physical locations. When disabled the "
                       "tenant operates from a single implicit branch.",
        "forced": False,
    },
    {
        "key": "terminals",
        "label": "Terminals & cash sessions",
        "group": "Multi-location",
        "description": "POS terminal registration and cashier shift "
                       "open/close flow.",
        "forced": False,
    },
    {
        "key": "inventory",
        "label": "Inventory tracking",
        "group": "Multi-location",
        "description": "Stock levels, movements, adjustments, transfers, "
                       "stock audits.",
        "forced": False,
    },
    # --- Operations ---
    {
        "key": "returns",
        "label": "Returns",
        "group": "Operations",
        "description": "Customer returns workflow.",
        "forced": False,
    },
    {
        "key": "debit_credit_notes",
        "label": "Debit / credit notes",
        "group": "Operations",
        "description": "Issue follow-up notes against existing FBR-"
                       "validated invoices for forgotten items or "
                       "amendments.",
        "forced": False,
    },
    {
        "key": "manual_amendments",
        "label": "Manual FBR amendments",
        "group": "Operations",
        "description": "Phase 4 manual-amendment workflow including "
                       "Annexure-C linkage.",
        "forced": False,
    },
    {
        "key": "payments_advanced",
        "label": "Cheques + bank transfers",
        "group": "Operations",
        "description": "Beyond cash and card — cheques, bank refs, "
                       "wallet payment tracking.",
        "forced": False,
    },
    {
        "key": "customer_display",
        "label": "Customer-facing display",
        "group": "Operations",
        "description": "The second-monitor display showing the running "
                       "cart and post-sale thank-you.",
        "forced": False,
    },
    {
        "key": "hardware",
        "label": "Hardware integrations",
        "group": "Operations",
        "description": "Thermal printer, barcode scanner, cash drawer "
                       "kick.",
        "forced": False,
    },
    # --- Restaurant (F&B vertical) ---
    {
        "key": "restaurant",
        "label": "Restaurant / F&B",
        "group": "Restaurant",
        "description": "Dine-in / takeaway / delivery orders, tables + "
                       "floor map, menu modifiers (add-ons / sizes), "
                       "kitchen tickets (KOT) + kitchen display. Gates the "
                       "restaurant API; pair with the 'restaurant' vertical "
                       "to surface the UI.",
        "forced": False,
    },
    # --- Insights ---
    {
        "key": "reports_basic",
        "label": "Reports — basic",
        "group": "Insights",
        "description": "Daily summary, today's sales, simple lookups.",
        "forced": False,
    },
    {
        "key": "reports_advanced",
        "label": "Reports — advanced",
        "group": "Insights",
        "description": "Stock valuation, scheduled reports, period "
                       "comparisons, exports.",
        "forced": False,
    },
    {
        "key": "audit_log",
        "label": "Audit log",
        "group": "Insights",
        "description": "Six-year-retention audit trail viewer.",
        "forced": False,
    },
]

# All known module keys. Used to validate input and drive the default for
# new tenants ("everything on") so existing tenants don't lose access on
# migration.
MODULE_KEYS: list[str] = [m["key"] for m in MODULES]

# Modules that the platform refuses to let an operator turn off. Even if
# the JSON omits them, is_module_enabled returns True.
FORCED_MODULE_KEYS: set[str] = {m["key"] for m in MODULES if m["forced"]}


def default_modules_enabled() -> list[str]:
    """Default for new and existing tenants on migration: everything on.

    Super-admin trims down per tenant afterward. This avoids surprise
    lockouts when the field is added to live data.
    """
    return list(MODULE_KEYS)


def is_module_enabled(tenant, module_key: str) -> bool:
    """Authoritative check used by the HasModule permission and the
    /api/me/modules/ endpoint. Forced modules ignore tenant config.
    """
    if module_key in FORCED_MODULE_KEYS:
        return True
    enabled = getattr(tenant, "modules_enabled", None) or []
    return module_key in enabled


def normalise(values) -> list[str]:
    """Filter incoming module key list to only those defined in the
    catalog, preserve catalog ordering, and ensure forced modules are
    always present. Used by the admin form when an operator submits the
    checkbox grid.
    """
    if not values:
        cleaned = set()
    else:
        cleaned = {v for v in values if v in MODULE_KEYS}
    cleaned |= FORCED_MODULE_KEYS
    # Preserve catalog order (deterministic JSON for diffing).
    return [k for k in MODULE_KEYS if k in cleaned]
