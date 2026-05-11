"""Auth + user serializers."""

from __future__ import annotations

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant, TenantMembership

from .models import User


class TenantBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "business_name", "ntn", "subscription_status")


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # is_platform_staff is exposed so the login form can give a
        # specific error message ("super-admin account, use /admin/")
        # vs a generic ("no tenant access").
        fields = (
            "id", "email", "full_name", "preferred_language",
            "is_staff", "is_platform_staff",
        )


class PosTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login that embeds tenant_id + role in the access token.

    If the user has exactly one active membership, that's used. Otherwise the
    request must specify tenant_id (header or body).
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        membership = _resolve_membership(user)
        if membership:
            token["tenant_id"] = str(membership.tenant_id)
            token["role"] = membership.role
        # Phase 0 platform stub: platform-staff claims travel on the JWT
        # so middleware can gate tenant-side endpoints without an extra
        # DB roundtrip per request.
        token["is_platform_staff"] = bool(getattr(user, "is_platform_staff", False))
        token["platform_role"] = getattr(user, "platform_role", "") or ""
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        membership = _resolve_membership(self.user)
        data["user"] = UserBriefSerializer(self.user).data
        if membership:
            data["tenant"] = TenantBriefSerializer(membership.tenant).data
            data["role"] = membership.role
        else:
            data["tenant"] = None
            data["role"] = None
        return data


def _resolve_membership(user):
    return (
        TenantMembership.objects
        .select_related("tenant")
        .filter(user=user, is_active=True)
        .order_by("created_at")
        .first()
    )


class PinLoginSerializer(serializers.Serializer):
    """Cashier PIN login. Online-only in Phase 0; offline path lands in Phase 3.

    Inputs:
      - email: identifies the cashier (a terminal-side cache makes this fast).
      - pin: 4-6 digit PIN, hashed-checked against User.pin_hash.

    Phase 0 simplification: we trust email + PIN. In Phase 3 we'll add
    terminal_id (device fingerprint) so a stolen PIN can't be used away from
    its assigned terminal.
    """

    email = serializers.EmailField()
    pin = serializers.RegexField(regex=r"^\d{4,6}$")

    def validate(self, attrs):
        email = attrs["email"].lower()
        pin = attrs["pin"]
        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("Invalid email or PIN.") from exc

        if not user.check_pin(pin):
            raise serializers.ValidationError("Invalid email or PIN.")

        membership = _resolve_membership(user)
        if not membership:
            raise serializers.ValidationError("User has no active tenant membership.")

        refresh = RefreshToken.for_user(user)
        refresh["tenant_id"] = str(membership.tenant_id)
        refresh["role"] = membership.role
        refresh["is_platform_staff"] = bool(user.is_platform_staff)
        refresh["platform_role"] = user.platform_role or ""

        attrs["user"] = user
        attrs["tenant"] = membership.tenant
        attrs["role"] = membership.role
        attrs["access"] = str(refresh.access_token)
        attrs["refresh"] = str(refresh)
        return attrs

    def to_representation(self, instance):
        return {
            "access": instance["access"],
            "refresh": instance["refresh"],
            "user": UserBriefSerializer(instance["user"]).data,
            "tenant": TenantBriefSerializer(instance["tenant"]).data,
            "role": instance["role"],
        }
