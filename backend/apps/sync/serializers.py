"""Sync API serializers — wire format from POS to server."""

from __future__ import annotations

from rest_framework import serializers

from .models import SyncLog


class _LineSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=4)
    discount_pct = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, default=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    is_taxable = serializers.BooleanField(default=True)


class _PaymentSerializer(serializers.Serializer):
    payment_method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)


class IngestInvoiceSerializer(serializers.Serializer):
    """POST /api/sync/invoices/."""
    client_uuid = serializers.UUIDField()
    terminal = serializers.UUIDField()
    branch = serializers.UUIDField()
    cashier = serializers.UUIDField()
    cash_session = serializers.UUIDField(required=False, allow_null=True)
    customer = serializers.UUIDField(required=False, allow_null=True)

    local_invoice_number = serializers.CharField(max_length=40)
    cart_lines = _LineSerializer(many=True)
    cart_discount_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    payments = _PaymentSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class IngestCustomerSerializer(serializers.Serializer):
    """POST /api/sync/customers/."""
    client_uuid = serializers.UUIDField()
    id = serializers.UUIDField(required=False)   # POS-generated if create
    op = serializers.ChoiceField(choices=["create", "update"], default="create")
    updated_at = serializers.DateTimeField()

    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    cnic = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=15)
    ntn = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    registration_type = serializers.ChoiceField(
        choices=["registered", "unregistered"], default="unregistered",
    )
    province = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    address = serializers.CharField(required=False, allow_blank=True, default="")
    store_credit = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, default=0,
    )


class SyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncLog
        fields = (
            "id", "tenant", "terminal", "client_uuid",
            "entity_type", "entity_id", "action",
            "status", "error_message",
            "received_at", "processed_at",
        )
        read_only_fields = fields


class TerminalSyncStatusSerializer(serializers.Serializer):
    terminal = serializers.UUIDField()
    pending = serializers.IntegerField()
    failed = serializers.IntegerField()
    last_processed_at = serializers.DateTimeField(allow_null=True)
    last_seen_at = serializers.DateTimeField(allow_null=True)
