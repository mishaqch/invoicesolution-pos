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
    Warehouse,
)


class WarehouseSerializer(serializers.ModelSerializer):
    # Embed the branch name so the DI UI never has to call /branches/ (that
    # endpoint is gated behind the `branches` module, which DI tenants lack).
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = (
            "id", "branch", "branch_name", "name", "code",
            "city", "address",
            "is_default", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "branch_name", "created_at", "updated_at")


class StockLevelSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    # FBR-relevant product metadata, read-only, so the stock view doubles as the
    # FBR cockpit: it shows the full fiscal identity (HS code, UoM, sale type,
    # SRO, retail price) per item without a separate products fetch + lookup.
    # These mirror Product (the single source of truth) — the Stock screen EDITS
    # them by PATCHing /catalog/products/{id}/, it does NOT store a second copy.
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_description = serializers.CharField(source="product.description", read_only=True)
    hs_code = serializers.CharField(source="product.hs_code_id", read_only=True)
    uom = serializers.CharField(source="product.uom_id", read_only=True)
    sale_type = serializers.CharField(source="product.sale_type", read_only=True)
    sro_schedule_no = serializers.CharField(source="product.sro_schedule_no", read_only=True)
    sro_item_serial_no = serializers.CharField(source="product.sro_item_serial_no", read_only=True)
    tax_rate = serializers.CharField(source="product.tax_rate_id", read_only=True, allow_null=True)
    retail_price = serializers.DecimalField(
        source="product.retail_price", max_digits=14, decimal_places=4,
        read_only=True, allow_null=True,
    )
    is_third_schedule = serializers.BooleanField(source="product.is_third_schedule", read_only=True)

    class Meta:
        model = StockLevel
        fields = (
            "id", "product", "product_name", "product_sku", "product_description",
            "hs_code", "uom", "sale_type",
            "sro_schedule_no", "sro_item_serial_no",
            "tax_rate", "retail_price", "is_third_schedule",
            "variant", "branch", "warehouse", "warehouse_name",
            "quantity", "reserved_quantity", "reorder_level",
            "last_counted_at", "updated_at",
        )
        read_only_fields = (
            "id", "warehouse_name", "product_name", "product_sku",
            "product_description", "hs_code", "uom", "sale_type",
            "sro_schedule_no", "sro_item_serial_no",
            "tax_rate", "retail_price", "is_third_schedule", "updated_at",
        )


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = (
            "id", "product", "variant", "batch", "branch", "warehouse",
            "movement_type", "quantity", "unit_cost",
            "reference_type", "reference_id",
            "reason", "performed_by", "created_at",
        )
        read_only_fields = ("id", "created_at")


class AdjustmentSerializer(serializers.Serializer):
    """Body of POST /api/inventory/adjustments/."""
    branch = serializers.UUIDField()
    # Optional warehouse — when set (Digital Invoicing), the adjustment is
    # recorded against that warehouse's stock level. When omitted (POS), the
    # adjustment is branch-keyed exactly as before.
    warehouse = serializers.UUIDField(required=False, allow_null=True)
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
