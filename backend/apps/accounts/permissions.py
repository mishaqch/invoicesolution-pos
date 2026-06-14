"""Role-permission matrix per DATABASE_SCHEMA.md §1.

This is the seeding for the role permission catalog. The row-level checks
that consult this map are wired in DRF permission classes per app as we ship
each phase. Phase 0 only needs the data + a base IsTenantMember permission.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

# perm-key -> set of roles that have it by default
DEFAULT_ROLE_PERMS: dict[str, set[str]] = {
    "sales.create":                       {"owner", "manager", "cashier"},
    "sales.cancel.threshold_low":         {"owner", "manager", "cashier"},
    "sales.cancel.threshold_high":        {"owner", "manager"},
    "inventory.adjust":                   {"owner", "manager"},
    "products.manage":                    {"owner", "manager"},
    "users.manage":                       {"owner"},
    "fbr.tokens.manage":                  {"owner"},
    "reports.view.all_branches":          {"owner", "accountant", "auditor"},
    "reports.view.own_branch":            {"owner", "manager", "accountant", "auditor"},
    "audit_log.view":                     {"owner", "accountant", "auditor"},
    "settings.business_profile":          {"owner"},
}


def role_has_perm(role: str, perm: str) -> bool:
    return role in DEFAULT_ROLE_PERMS.get(perm, set())


# Plain-English summary of what each role can do, shown in the Django
# admin's TenantMembership inline so super-admin operators can pick a
# role without memorising the permission matrix.
#
# Keep these synced with DEFAULT_ROLE_PERMS above.
ROLE_DESCRIPTIONS: dict[str, str] = {
    "owner":
        "Full access. Create + cancel invoices, manage users + FBR "
        "tokens, edit business profile, see every branch's reports, "
        "view audit log. The buck stops here.",
    "manager":
        "Operational manager. Create + cancel invoices (any amount), "
        "adjust inventory, manage products + customers, see own "
        "branch's reports. Cannot manage users or FBR tokens.",
    "cashier":
        "Front-of-house. Ring up sales, accept payments, cancel "
        "low-value sales. Cannot adjust inventory, manage products, "
        "or see reports beyond today's totals.",
    "accountant":
        "Finance role. View invoices + payments + ledger across all "
        "branches, view audit log, run reports. Read-only for sales "
        "and inventory — does not create invoices.",
    "auditor":
        "External / compliance read-only. View invoices, FBR "
        "submissions, audit log, all-branch reports. Cannot edit "
        "anything.",
}


def role_description(role: str) -> str:
    """Return the plain-English summary for a role."""
    return ROLE_DESCRIPTIONS.get(role, f"Custom role: {role}")


def all_perms_for_role(role: str) -> list[str]:
    """Return the list of perm keys this role has. Useful for showing
    a "what does this role unlock?" chip list in the admin."""
    return sorted(p for p, roles in DEFAULT_ROLE_PERMS.items() if role in roles)


class IsTenantMember(BasePermission):
    """Authenticated + has an active membership in some tenant on this request."""

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(request, "tenant_id", None) is not None


class HasRolePerm(BasePermission):
    """Permission class that checks the role-permission matrix.

    Usage:
        class MyView(APIView):
            permission_classes = [HasRolePerm.with_perm("products.manage")]

    Read-only verbs (GET/HEAD/OPTIONS) only require IsTenantMember + the
    `read_perm` if specified. Write verbs require `write_perm`.
    """

    read_perm: str | None = None
    write_perm: str | None = None

    @classmethod
    def with_perm(
        cls,
        write_perm: str,
        read_perm: str | None = None,
    ) -> type["HasRolePerm"]:
        return type(
            "HasRolePermBound",
            (cls,),
            {"write_perm": write_perm, "read_perm": read_perm},
        )

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if not getattr(request, "tenant_id", None):
            return False

        membership = getattr(request, "tenant_membership", None)
        if not membership:
            return False

        is_read = request.method in ("GET", "HEAD", "OPTIONS")
        perm = self.read_perm if is_read else self.write_perm
        if not perm:
            return is_read  # read with no perm == any tenant member; write must declare a perm
        return role_has_perm(membership.role, perm)


class HasModule(BasePermission):
    """Gate access to a module the super-admin has not enabled for this tenant.

    Modules are coarser than role permissions — they answer "should this
    tenant see Inventory at all?" while HasRolePerm answers "can this
    user adjust stock?". Both classes are typically composed:

        permission_classes = [
            HasRolePerm.with_perm("inventory.adjust"),
            HasModule.for_module("inventory"),
        ]

    Forced modules (sales, fbr) always pass — see apps.tenants.modules.
    """

    module_key: str | None = None

    @classmethod
    def for_module(cls, module_key: str) -> type["HasModule"]:
        return type(
            "HasModuleBound",
            (cls,),
            {"module_key": module_key},
        )

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            return False
        if self.module_key is None:
            # Misconfigured view — treat as deny so the bug is loud.
            return False

        # Lazy import to avoid pulling tenants.models during accounts import.
        from apps.tenants.models import Tenant
        from apps.tenants.modules import is_module_enabled

        try:
            tenant = Tenant.objects.only("modules_enabled").get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return False
        return is_module_enabled(tenant, self.module_key)

    def message(self):
        return (
            f"This tenant does not have the '{self.module_key}' module "
            f"enabled. Contact your platform administrator."
        )


class HasAnyModule(BasePermission):
    """Pass if the tenant has ANY one of the given modules enabled.

    Used by endpoints shared between two tenant shapes — e.g. stock levels +
    adjustments, which POS tenants reach via the `inventory` module and
    Digital-Invoicing tenants reach via the `warehouses` module.
    """

    module_keys: tuple[str, ...] = ()

    @classmethod
    def for_modules(cls, *module_keys: str) -> type["HasAnyModule"]:
        return type(
            "HasAnyModuleBound",
            (cls,),
            {"module_keys": tuple(module_keys)},
        )

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id or not self.module_keys:
            return False

        from apps.tenants.models import Tenant
        from apps.tenants.modules import is_module_enabled

        try:
            tenant = Tenant.objects.only("modules_enabled").get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return False
        return any(is_module_enabled(tenant, key) for key in self.module_keys)

    def message(self):
        keys = "', '".join(self.module_keys)
        return (
            f"This tenant has none of the required modules ('{keys}') "
            f"enabled. Contact your platform administrator."
        )
