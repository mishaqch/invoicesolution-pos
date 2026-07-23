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
    # Restaurant (optional; ignored for other verticals). modifiers is a list of
    # {name, price} snapshots whose deltas are already in unit_price.
    modifiers = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    course = serializers.IntegerField(required=False, allow_null=True)
    item_note = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)


class _PaymentSerializer(serializers.Serializer):
    payment_method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)

    # Method-specific proof fields the POS terminal collects (card slip, wallet
    # tx id, cheque number, …). All optional here; the per-method adapter owns
    # which are required. Without these a plain Serializer DROPS them and card
    # sales fail server-side with "card_last4: Required." even though the
    # cashier keyed the slip. Mirrors CheckoutPaymentSerializer.
    card_last4 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    card_auth_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    card_rrn = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    card_terminal_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    wallet_transaction_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    wallet_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    raast_transaction_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    raast_iban = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cheque_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cheque_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_account_last4 = serializers.CharField(required=False, allow_blank=True, allow_null=True)


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
    # Restaurant order-level (optional; null for other verticals).
    order_type = serializers.ChoiceField(
        choices=["dine_in", "takeaway", "delivery"], required=False, allow_null=True,
    )
    table = serializers.UUIDField(required=False, allow_null=True)
    covers = serializers.IntegerField(required=False, allow_null=True)


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
