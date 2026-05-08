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
