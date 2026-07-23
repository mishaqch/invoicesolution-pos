"""Auth + user serializers."""

from __future__ import annotations

import logging

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant, TenantMembership

from .models import User

logger = logging.getLogger(__name__)


class TenantBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = (
            "id", "business_name", "ntn", "subscription_status", "logo_url",
            # address + phone feed the POS thermal-receipt header.
            "address", "phone",
            # vertical drives pharmacy-only UI on the terminal (e.g. FEFO).
            "vertical",
            # fbr_connection_type="none" → terminal prints plain non-fiscal
            # receipts (no FBR QR/number) and hides FBR-specific UI.
            "fbr_connection_type",
            # modules_enabled lets the terminal gate optional features — e.g. the
            # `hotel` module surfaces the Stays/Rooms (guest folio) flow.
            "modules_enabled",
            # Payment-driven services tax rates: the terminal recomputes services
            # tax at checkout from the selected payment method (card → reduced).
            "services_tax_rate_standard", "services_tax_rate_card",
        )


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
      - pin: exactly 6 digit PIN, hashed-checked against User.pin_hash.

    Why exactly 6 (and not the older 4-6 range): the terminal UI shows
    a 6-dot indicator and auto-submits when the PIN field reaches the
    minimum length. A 4-6 range meant typing a 6-digit PIN caused the
    terminal to auto-submit at digit 4 with the partial value, fail
    auth, clear the PIN field, then route digits 5+6 into an empty
    field — making 6-digit PINs effectively un-loggable. Standardising
    on 6 digits removes the auto-submit ambiguity entirely.

    Phase 0 simplification: we trust email + PIN. In Phase 3 we'll add
    terminal_id (device fingerprint) so a stolen PIN can't be used away from
    its assigned terminal.
    """

    email = serializers.EmailField()
    pin = serializers.RegexField(regex=r"^\d{6}$")

    def validate(self, attrs):
        # Normalize defensively: trim whitespace and lowercase. The
        # terminal also normalizes client-side, but we mirror it here
        # so PIN-login over the raw API (curl, integration tests) is
        # equally forgiving.
        raw_email = attrs["email"] or ""
        email = raw_email.strip().lower()
        pin = attrs["pin"]
        # Dev-mode diagnostic: helps trace "the PIN works in curl but
        # not from the terminal" mysteries. Logs the *shape* of the
        # inputs, never the PIN itself.
        logger.info(
            "pin-login attempt: raw_email_len=%d clean_email=%r pin_len=%d",
            len(raw_email), email, len(pin),
        )
        try:
            # iexact = case-insensitive exact match. Belt-and-braces:
            # `email` is already lowercased above, but the column
            # collation in some Postgres setups is case-sensitive and
            # users may have been saved with mixed case before this
            # serializer started normalizing.
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist as exc:
            logger.info("pin-login: user not found for email=%r", email)
            raise serializers.ValidationError("Invalid email or PIN.") from exc

        if not user.check_pin(pin):
            logger.info("pin-login: bad PIN for user=%s", user.email)
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


# Roles allowed to authorize a void/edit/discount at the till.
SUPERVISOR_ROLES = frozenset({"owner", "manager"})


class SupervisorPinVerifySerializer(serializers.Serializer):
    """Verify a manager/owner PIN to AUTHORIZE a till action (void/edit/
    discount) — WITHOUT issuing a session token.

    Security:
      - The PIN must belong to an ACTIVE owner/manager of the SAME tenant the
        terminal is operating in (tenant_id from the verified request, not the
        body) — a cashier PIN, or a manager from another tenant, is rejected.
      - Generic "Invalid email or PIN" so we never reveal which part was wrong
        or whether an email exists.
      - No tokens minted; the caller just learns valid + role.
    """

    email = serializers.EmailField()
    pin = serializers.RegexField(regex=r"^\d{6}$")

    def validate(self, attrs):
        tenant_id = self.context.get("tenant_id")
        if not tenant_id:
            raise serializers.ValidationError("Tenant context required.")

        email = (attrs["email"] or "").strip().lower()
        pin = attrs["pin"]

        generic = serializers.ValidationError(
            "Invalid PIN, or this account can't authorize this action.",
        )
        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist as exc:
            raise generic from exc
        if not user.check_pin(pin):
            raise generic

        # Must be an active owner/manager OF THIS tenant.
        membership = (
            TenantMembership.objects
            .filter(user=user, tenant_id=tenant_id, is_active=True)
            .first()
        )
        if not membership or membership.role not in SUPERVISOR_ROLES:
            raise generic

        attrs["user"] = user
        attrs["role"] = membership.role
        return attrs
