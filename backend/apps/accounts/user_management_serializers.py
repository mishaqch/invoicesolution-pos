"""Serializers for tenant staff (cashier / user) management.

The managed resource is the TenantMembership (tenant + user + role + branches +
is_active), flattened with the user's identity. A User can belong to several
tenants, so deactivation is membership-scoped and creation reuses an existing
User row when the email already exists. pin_hash is NEVER serialized — only a
`has_pin` boolean; PINs are set write-only via `pin` / the set-pin action.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.tenants.models import ROLES, TenantMembership

from .models import User

PIN_REGEX = r"^\d{6}$"


class MembershipSerializer(serializers.ModelSerializer):
    """List / retrieve / update representation of a staff member."""

    # User identity (read-only except full_name / preferred_language on update).
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name")
    preferred_language = serializers.CharField(
        source="user.preferred_language", required=False,
    )
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    has_pin = serializers.SerializerMethodField()

    class Meta:
        model = TenantMembership
        fields = (
            "id", "user_id",
            "email", "full_name", "preferred_language",
            "role", "branch_ids", "is_active",
            "has_pin", "last_login", "created_at",
        )
        read_only_fields = ("id", "user_id", "created_at")

    def get_has_pin(self, obj) -> bool:
        return bool(obj.user.pin_hash)

    def update(self, instance, validated_data):
        # Split off the nested user writes (full_name / preferred_language).
        user_data = validated_data.pop("user", {})
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        # instance.save() runs TenantMembership.clean() → last-owner guard.
        instance.save()
        if user_data:
            for attr, value in user_data.items():
                setattr(instance.user, attr, value)
            instance.user.save(update_fields=[*user_data.keys(), "updated_at"])
        return instance


class MembershipCreateSerializer(serializers.Serializer):
    """Add a staff member. Attaches an existing User (by email) or creates one."""

    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=[r[0] for r in ROLES])
    branch_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    preferred_language = serializers.CharField(required=False, default="en")
    # Optional initial PIN (only applied when we CREATE the user; for an
    # existing user, set it afterwards via the set-pin action).
    pin = serializers.RegexField(PIN_REGEX, required=False, allow_blank=True, write_only=True)

    def validate_email(self, value: str) -> str:
        return (value or "").strip().lower()

    def create(self, validated_data):
        tenant_id = self.context["tenant_id"]
        email = validated_data["email"]
        role = validated_data["role"]
        branch_ids = validated_data.get("branch_ids", [])
        lang = validated_data.get("preferred_language") or "en"
        pin = validated_data.get("pin") or ""

        user = User.objects.filter(email__iexact=email).first()
        if user:
            # Attach an existing user (from another tenant, or re-added). Reuse
            # their identity — don't silently overwrite name/language/PIN.
            if TenantMembership.objects.filter(tenant_id=tenant_id, user=user).exists():
                raise serializers.ValidationError(
                    {"email": "This user is already a member of this business."},
                )
        else:
            user = User(email=email, full_name=validated_data["full_name"],
                        preferred_language=lang)
            user.set_unusable_password()  # cashiers log in by PIN, not password
            if pin:
                user.set_pin(pin)         # enforces 6-digit + hashes
            user.save()

        membership = TenantMembership(
            tenant_id=tenant_id, user=user, role=role,
            branch_ids=[str(b) for b in branch_ids], is_active=True,
        )
        membership.save()  # runs clean() guard
        return membership

    def to_representation(self, instance):
        return MembershipSerializer(instance, context=self.context).data


class SetPinSerializer(serializers.Serializer):
    pin = serializers.RegexField(PIN_REGEX)
