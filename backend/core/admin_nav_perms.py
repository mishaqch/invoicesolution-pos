"""Permission callbacks for the Django super-admin sidebar nav.

Unfold's sidebar config takes a `permission` callable per item (and
per section). The callable receives `request` and returns True/False —
return False and the item/section is hidden in the rendered sidebar.

We hide items the current user can't access so the nav matches what
operators actually see in the rest of the admin. Without this, a
delegated billing_admin who only has User/Tenant/Billing bundles
still saw the "Operations" group (FBR, Invoices, Audit log) — even
though clicking those would 403.

Each helper here is a callable that checks `user.has_perm(...)`.
Superusers see everything (Django's `has_perm` returns True for
is_superuser regardless of the explicit permission rows).
"""

from __future__ import annotations

from typing import Callable

from django.http import HttpRequest


def _has_any(*perms: str) -> Callable[[HttpRequest], bool]:
    """Return a callback that returns True if the request user has
    at least ONE of the given permission codes. Superusers always
    pass (Django's has_perm short-circuits)."""
    def check(request: HttpRequest) -> bool:
        u = request.user
        if not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        return any(u.has_perm(p) for p in perms)
    return check


# Per-section gates. The section is hidden when the callback returns
# False. A section hides only when EVERY item inside is also hidden —
# we still apply a section-level gate for slight efficiency.

# Tenants section: anyone who can view tenants OR branches OR cashiers.
tenants_section = _has_any(
    "tenants.view_tenant", "tenants.view_branch", "tenants.view_terminal",
    "tenants.view_cashier",
)

# Billing section: anyone with view perm on plan / subscription / settings.
billing_section = _has_any(
    "platform_admin.view_subscriptionplan",
    "platform_admin.view_subscription",
    "platform_admin.view_platformsettings",
)

# People section: anyone who can view users or groups.
people_section = _has_any("accounts.view_user", "auth.view_group")

# Operations section: FBR / invoices / audit log.
operations_section = _has_any(
    "fbr.view_fbrsubmission",
    "fbr.view_fbrtoken",
    "sales.view_invoice",
    "audit.view_auditlog",
)


# Per-item gates. Same pattern but item-specific.

view_tenant = _has_any("tenants.view_tenant")
view_branch = _has_any("tenants.view_branch")
view_terminal = _has_any("tenants.view_terminal")
view_cashier = _has_any("tenants.view_cashier")

view_subscription_plan = _has_any("platform_admin.view_subscriptionplan")
view_subscription = _has_any("platform_admin.view_subscription")
view_platform_settings = _has_any("platform_admin.view_platformsettings")

view_user = _has_any("accounts.view_user")
view_group = _has_any("auth.view_group")

view_fbr_submission = _has_any("fbr.view_fbrsubmission")
view_fbr_token = _has_any("fbr.view_fbrtoken")
view_invoice = _has_any("sales.view_invoice")
view_audit_log = _has_any("audit.view_auditlog")
