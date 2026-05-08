"""Returns API serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import Return, ReturnItem


class ReturnItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnItem
        fields = (
            "id", "original_sale_item",
            "product", "variant",
            "quantity", "unit_price", "tax_amount", "line_total",
            "restocked", "movement_type",
        )
        read_only_fields = fields


class ReturnSerializer(serializers.ModelSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)

    class Meta:
        model = Return
        fields = (
            "id", "branch", "terminal", "cashier", "customer",
            "original_invoice",
            "return_number", "fbr_credit_note_number", "return_date",
            "reason", "reason_notes",
            "refund_method", "refund_amount",
            "fbr_route", "status",
            "client_uuid", "items",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "return_number", "fbr_credit_note_number",
            "fbr_route", "status",
            "created_at", "updated_at",
        )


class ProcessReturnSerializer(serializers.Serializer):
    """Body of POST /api/returns/."""
    original_invoice = serializers.UUIDField()
    branch = serializers.UUIDField()
    terminal = serializers.UUIDField()
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )
    reason = serializers.ChoiceField(
        choices=["damaged", "wrong_item", "customer_changed_mind",
                 "expired", "other"],
    )
    reason_notes = serializers.CharField(required=False, allow_blank=True, default="")
    refund_method = serializers.ChoiceField(
        choices=["cash", "store_credit", "card_reversal",
                 "wallet_reversal", "bank_transfer"],
    )
    refund_data = serializers.DictField(required=False, default=dict)
    client_uuid = serializers.UUIDField(required=False)
