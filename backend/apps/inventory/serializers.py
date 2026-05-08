"""Inventory DRF serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    StockAudit,
    StockAuditItem,
    StockLevel,
    StockMovement,
    StockTransfer,
    StockTransferItem,
)


class StockLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLevel
        fields = (
            "id", "product", "variant", "branch",
            "quantity", "reserved_quantity", "reorder_level",
            "last_counted_at", "updated_at",
        )
        read_only_fields = ("id", "updated_at")


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = (
            "id", "product", "variant", "batch", "branch",
            "movement_type", "quantity", "unit_cost",
            "reference_type", "reference_id",
            "reason", "performed_by", "created_at",
        )
        read_only_fields = ("id", "created_at")


class AdjustmentSerializer(serializers.Serializer):
    """Body of POST /api/inventory/adjustments/."""
    branch = serializers.UUIDField()
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4)
    reason = serializers.CharField(allow_blank=False)
    movement_type = serializers.ChoiceField(
        choices=["adjustment_in", "adjustment_out", "damage", "expiry", "opening_balance"]
    )


class StockTransferItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransferItem
        fields = (
            "id", "transfer", "product", "variant",
            "quantity_dispatched", "quantity_received", "variance",
        )
        read_only_fields = ("id", "quantity_received", "variance")


class StockTransferSerializer(serializers.ModelSerializer):
    items = StockTransferItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockTransfer
        fields = (
            "id", "transfer_number",
            "from_branch", "to_branch",
            "status",
            "dispatched_at", "dispatched_by",
            "received_at", "received_by",
            "notes", "items",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "status", "dispatched_at", "dispatched_by",
            "received_at", "received_by", "created_at", "updated_at",
        )


class StockAuditItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAuditItem
        fields = (
            "id", "audit", "product", "variant",
            "expected_quantity", "counted_quantity",
            "variance", "variance_reason",
        )
        read_only_fields = ("id",)


class StockAuditSerializer(serializers.ModelSerializer):
    items = StockAuditItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockAudit
        fields = (
            "id", "branch", "audit_number", "status",
            "started_at", "finalized_at", "performed_by",
            "notes", "items",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "status", "finalized_at", "created_at", "updated_at")
