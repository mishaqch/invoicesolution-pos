"""Tenant staff (cashier / user) management API — /api/users/.

Owner + manager (users.manage) can list/search staff, add users, edit role /
branches / active state, remove them from the tenant, and set/reset the 6-digit
terminal PIN. A manager can NOT create, edit, promote-to, or remove an owner —
that's owner-only. The last active owner can't be orphaned (enforced in the
TenantMembership model). PINs are never returned.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import HasRolePerm
from apps.audit.services import log as audit_log
from apps.tenants.models import Branch, TenantMembership

from .user_management_serializers import (
    MembershipCreateSerializer,
    MembershipSerializer,
    SetPinSerializer,
)


class MembershipViewSet(viewsets.ModelViewSet):
    """CRUD + set-pin for a tenant's staff memberships."""

    permission_classes = [HasRolePerm.with_perm("users.manage", read_perm="users.manage")]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        return MembershipCreateSerializer if self.action == "create" else MembershipSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant_id"] = getattr(self.request, "tenant_id", None)
        return ctx

    def get_queryset(self):
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return TenantMembership.objects.none()
        qs = (
            TenantMembership.objects.select_related("user")
            .filter(tenant_id=tenant_id)
            .order_by("user__full_name")
        )
        p = self.request.query_params
        if (search := (p.get("search") or "").strip()):
            from django.db.models import Q
            qs = qs.filter(
                Q(user__full_name__icontains=search) | Q(user__email__icontains=search),
            )
        if (role := p.get("role")):
            qs = qs.filter(role=role)
        if (active := p.get("is_active")) in ("true", "false"):
            qs = qs.filter(is_active=(active == "true"))
        return qs

    # --- role guards --------------------------------------------------------

    def _actor_role(self) -> str:
        return getattr(self.request.tenant_membership, "role", "")

    def _guard_owner_action(self, *, role_before: str | None = None, role_after: str | None = None):
        """Only an owner may create, edit, promote-to, or remove an OWNER."""
        if self._actor_role() == "owner":
            return
        if role_before == "owner" or role_after == "owner":
            raise PermissionDenied("Only an owner can add, edit, or promote owners.")

    # --- create -------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        self._guard_owner_action(role_after=ser.validated_data["role"])
        try:
            membership = ser.save()
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        audit_log(
            tenant_id=request.tenant_id, user=request.user, entity_type="user",
            entity_id=membership.user_id, action="member_added",
            after={"email": membership.user.email, "role": membership.role,
                   "branch_ids": [str(b) for b in membership.branch_ids]},
            request=request,
        )
        return Response(MembershipSerializer(membership, context=self.get_serializer_context()).data, status=201)

    # --- update -------------------------------------------------------------

    def perform_update(self, serializer):
        instance = serializer.instance
        role_before = instance.role
        role_after = serializer.validated_data.get("role", role_before)
        self._guard_owner_action(role_before=role_before, role_after=role_after)

        # Can't deactivate your own account (avoids a self-lockout with a
        # clearer message than the last-owner model guard).
        if (
            instance.user_id == self.request.user.id
            and serializer.validated_data.get("is_active") is False
        ):
            raise ValidationError("You cannot deactivate your own account.")

        before = {"role": role_before, "is_active": instance.is_active,
                  "branch_ids": [str(b) for b in instance.branch_ids]}
        try:
            membership = serializer.save()
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        after = {"role": membership.role, "is_active": membership.is_active,
                 "branch_ids": [str(b) for b in membership.branch_ids]}
        audit_log(
            tenant_id=self.request.tenant_id, user=self.request.user,
            entity_type="user", entity_id=membership.user_id,
            action="member_updated", before=before, after=after, request=self.request,
        )

    # --- destroy (remove from THIS tenant only) -----------------------------

    def perform_destroy(self, instance):
        self._guard_owner_action(role_before=instance.role)
        if instance.user_id == self.request.user.id:
            raise ValidationError("You cannot remove your own account.")
        email = instance.user.email
        try:
            instance.delete()  # model guards the last active owner
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        audit_log(
            tenant_id=self.request.tenant_id, user=self.request.user,
            entity_type="user", entity_id=instance.user_id, action="member_removed",
            after={"email": email}, request=self.request,
        )

    # --- set / reset PIN ----------------------------------------------------

    @action(detail=True, methods=["post"], url_path="set-pin")
    def set_pin(self, request, pk=None):
        membership = self.get_object()
        self._guard_owner_action(role_before=membership.role)
        ser = SetPinSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = membership.user
        user.set_pin(ser.validated_data["pin"])
        user.save(update_fields=["pin_hash", "updated_at"])
        audit_log(
            tenant_id=request.tenant_id, user=request.user, entity_type="user",
            entity_id=user.id, action="pin_reset", after={"target": user.email},
            request=request,
        )
        return Response({"has_pin": True})

    # --- branch options for the assign multi-select -------------------------

    @action(detail=False, methods=["get"], url_path="branch-options")
    def branch_options(self, request):
        """Lightweight branch list for the branch-assign control — so a manager
        (who can't hit /api/branches/) still gets branch labels."""
        branches = (
            Branch.objects.filter(tenant_id=request.tenant_id, deleted_at__isnull=True)
            .order_by("name")
            .values("id", "name", "code")
        )
        return Response([{"id": str(b["id"]), "name": b["name"], "code": b["code"]} for b in branches])
