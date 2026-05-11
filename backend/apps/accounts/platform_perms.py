"""Curated Django permission bundles for platform-staff users.

Django's stock `user_permissions` widget exposes the entire catalog
(~200 add/change/delete/view rows across every model in every app),
which is overwhelming and contains dangerous / never-useful options
(content types, JWT blacklist internals, materialized report tables,
permission/group rows themselves).

We replace that widget with a small set of OPERATOR-FRIENDLY BUNDLES.
Each bundle is one checkbox the super-admin can tick, and saving the
form translates that into the underlying Django Permission rows.

A bundle is read-only metadata. Editing the list of bundles or what
each one covers requires a code change — intentional, because the
underlying permission model is something we own, not something
operators tune ad hoc.

Bundle keys are arbitrary strings; the matching is done by the
(app_label, model_name) pairs in `models`. We ALWAYS include all four
verbs (add/change/delete/view) for the listed models — partial-CRUD
permission grants are a footgun and almost never what operators
actually want.
"""

from __future__ import annotations

from typing import TypedDict


class _Bundle(TypedDict):
    key: str
    label: str
    description: str
    # List of (app_label, model_name) tuples whose CRUD permissions
    # belong to this bundle.
    models: list[tuple[str, str]]


PLATFORM_PERMISSION_BUNDLES: list[_Bundle] = [
    {
        "key": "user_management",
        "label": "User management",
        "description": (
            "Create and edit platform staff + tenant users. "
            "Required for onboarding new operators and resetting "
            "passwords. Includes Groups (Django's role primitive)."
        ),
        "models": [
            ("accounts", "user"),
            ("auth", "group"),
        ],
    },
    {
        "key": "tenant_management",
        "label": "Tenant management",
        "description": (
            "Create / edit / suspend tenants, manage tenant "
            "memberships, view branches + terminals + cash sessions. "
            "Core onboarding + support permission."
        ),
        "models": [
            ("tenants", "tenant"),
            ("tenants", "tenantmembership"),
            ("tenants", "branch"),
            ("tenants", "terminal"),
            ("tenants", "tenantsettings"),
            ("tenants", "cashsession"),
        ],
    },
    {
        "key": "billing",
        "label": "Billing & subscriptions",
        "description": (
            "Manage subscription plans, edit per-tenant subscriptions, "
            "tweak global platform settings. For billing_admin / "
            "support_lead roles."
        ),
        "models": [
            ("platform_admin", "subscriptionplan"),
            ("platform_admin", "subscription"),
            ("platform_admin", "platformsettings"),
        ],
    },
    {
        "key": "fbr_operations",
        "label": "FBR operations",
        "description": (
            "View and triage FBR submissions, tokens, scenario tests, "
            "and the cancel-budget. The day-to-day surface for support "
            "agents chasing failed FBR validations."
        ),
        "models": [
            ("fbr", "fbrtoken"),
            ("fbr", "fbrsubmission"),
            ("fbr", "fbrscenariotest"),
            ("fbr", "fbrcancelbudget"),
            ("fbr", "fbrcancelbudgetconsumption"),
            ("fbr", "fbripwhitelist"),
        ],
    },
    {
        "key": "support_triage",
        "label": "Support triage (sales + customers + inventory)",
        "description": (
            "Read + edit tenant data to help debug support tickets — "
            "invoices, payments, customers, inventory, returns. "
            "Heavy access; reserve for support leads."
        ),
        "models": [
            ("sales", "invoice"),
            ("sales", "saleitem"),
            ("sales", "payment"),
            ("sales", "discount"),
            ("customers", "customer"),
            ("customers", "customergroup"),
            ("inventory", "stocklevel"),
            ("inventory", "stockmovement"),
            ("inventory", "stocktransfer"),
            ("inventory", "stockaudit"),
            ("returns", "return"),
        ],
    },
    {
        "key": "global_reference",
        "label": "Global reference data",
        "description": (
            "Edit the platform-wide HS code catalog + units of "
            "measure. Rare changes; usually only when FBR publishes "
            "new codes."
        ),
        "models": [
            ("catalog", "hscode"),
            ("catalog", "unitofmeasure"),
        ],
    },
    {
        "key": "audit_read",
        "label": "Audit log (read)",
        "description": (
            "View the immutable audit log. Required for compliance "
            "officers + serious incident investigation. Note: rows "
            "cannot be edited or deleted regardless of this permission."
        ),
        "models": [
            ("audit", "auditlog"),
        ],
    },
    {
        "key": "notifications_admin",
        "label": "Notifications administration",
        "description": (
            "Manage in-app notifications and sync logs. Rare; mainly "
            "for clearing stuck notifications during incidents."
        ),
        "models": [
            ("notifications", "notification"),
            ("sync", "synclog"),
        ],
    },
]


# Standard CRUD verbs — every bundle grants all four for every listed model.
_VERBS = ("add", "change", "delete", "view")

# Permission keys (codename) follow Django's `<verb>_<modelname>` pattern.
# We compute the full set this bundle covers, ignoring permissions whose
# content type isn't found (the DB query layer will filter by
# (app_label, codename) so missing models / unmigrated apps don't crash).


def bundle_perm_keys(bundle_key: str) -> set[tuple[str, str]]:
    """Return the (app_label, codename) set for one bundle. Useful when
    you want to do an exact-match query on the Permission table."""
    bundle = next(
        (b for b in PLATFORM_PERMISSION_BUNDLES if b["key"] == bundle_key),
        None,
    )
    if bundle is None:
        return set()
    return {
        (app_label, f"{verb}_{model_name}")
        for (app_label, model_name) in bundle["models"]
        for verb in _VERBS
    }


def all_bundle_perm_keys() -> set[tuple[str, str]]:
    """Union of every bundle's keys — the complete allow-list for the
    `user_permissions` widget. Anything NOT in this set never appears
    in the picker."""
    out: set[tuple[str, str]] = set()
    for b in PLATFORM_PERMISSION_BUNDLES:
        out |= bundle_perm_keys(b["key"])
    return out


def bundle_for_permission(app_label: str, codename: str) -> str | None:
    """Reverse lookup: given a single permission, which bundle owns it.
    Returns the bundle key (e.g. "tenant_management") or None.
    Used to derive which checkboxes to pre-tick when an existing user
    is loaded."""
    for b in PLATFORM_PERMISSION_BUNDLES:
        if (app_label, codename) in bundle_perm_keys(b["key"]):
            return b["key"]
    return None
