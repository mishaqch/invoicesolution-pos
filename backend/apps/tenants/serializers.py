"""Serializers for branches + terminals."""

from __future__ import annotations

from rest_framework import serializers

from .models import Branch, Terminal


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = (
            "id", "name", "code", "address", "city", "province", "phone",
            "is_active", "is_default", "fbr_pos_id", "fbr_pos_code",
            "receipt_header", "receipt_footer",
            "created_at", "updated_at", "deleted_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "deleted_at")


class TerminalSerializer(serializers.ModelSerializer):
    # Surface the pairing code + its state so admin-web can show it (with a
    # copy button) and indicate whether the terminal has paired yet. Both are
    # read-only here; the code is (re)issued via the dedicated issue-code action.
    is_paired = serializers.SerializerMethodField()
    # Optional on create: admin-web creates the terminal slot WITHOUT a real
    # device, and the pairing step stamps the machine's true fingerprint. The
    # view supplies an "unpaired-<uuid>" placeholder when this is omitted.
    device_fingerprint = serializers.CharField(
        max_length=128, required=False, allow_blank=True,
    )

    class Meta:
        model = Terminal
        fields = (
            "id", "branch", "name", "terminal_index", "device_fingerprint",
            "os_version", "app_version",
            "printer_config", "scanner_config", "drawer_config",
            "customer_display_enabled",
            "pairing_code", "pairing_code_expires_at", "paired_at", "is_paired",
            "is_active", "last_seen_at", "last_synced_at",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "terminal_index", "last_seen_at", "last_synced_at",
            "pairing_code", "pairing_code_expires_at", "paired_at", "is_paired",
            "created_at", "updated_at",
        )

    def get_is_paired(self, obj) -> bool:
        return obj.paired_at is not None


class TerminalPairSerializer(serializers.Serializer):
    """Body of the public POST /api/terminals/pair/ — code + device identity.

    No auth: the pairing code IS the bearer of trust (single-use, expiring,
    issued by the owner in admin-web). The terminal supplies its real device
    fingerprint, which we stamp onto the Terminal row so this physical machine
    is bound to this terminal slot.
    """

    pairing_code = serializers.CharField(max_length=16)
    device_fingerprint = serializers.CharField(max_length=128)
    os_version = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default="",
    )
    app_version = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default="",
    )
