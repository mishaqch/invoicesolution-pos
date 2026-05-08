"""Serializers for branches + terminals."""

from __future__ import annotations

from rest_framework import serializers

from .models import Branch, Terminal


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = (
            "id", "name", "code", "address", "city", "province", "phone",
            "is_active", "is_default", "fbr_pos_id",
            "receipt_header", "receipt_footer",
            "created_at", "updated_at", "deleted_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "deleted_at")


class TerminalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Terminal
        fields = (
            "id", "branch", "name", "device_fingerprint",
            "os_version", "app_version",
            "printer_config", "scanner_config", "drawer_config",
            "customer_display_enabled",
            "is_active", "last_seen_at", "last_synced_at",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "last_seen_at", "last_synced_at", "created_at", "updated_at",
        )
