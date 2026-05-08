"""Sales DRF serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import Invoice, Payment, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = (
            "id", "line_number",
            "product", "variant", "batch",
            "product_name", "product_sku", "hs_code", "uom_code", "sale_type",
            "quantity", "unit_price", "cost_price",
            "discount_pct", "discount_amount",
            "tax_rate", "tax_amount",
            "line_total",
            "is_edited", "is_cancelled", "edit_count",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id", "invoice", "customer",
            "payment_method", "amount",
            "card_last4", "card_auth_code", "card_rrn",
            "wallet_provider", "wallet_phone", "wallet_transaction_id",
            "bank_name", "bank_account_last4", "bank_reference",
            "raast_iban", "raast_transaction_id",
            "cheque_number", "cheque_date", "cheque_status",
            "status", "received_by", "notes",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class InvoiceSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id", "branch", "terminal", "cashier", "cash_session", "customer",
            "local_invoice_number",
            "fbr_invoice_number", "fbr_qr_payload",
            "fbr_submitted_at", "fbr_validated_at",
            "invoice_type", "invoice_date",
            "buyer_name", "buyer_ntn_cnic", "buyer_phone",
            "buyer_address", "buyer_province", "buyer_registration_type",
            "subtotal", "discount_total", "tax_total", "grand_total",
            "paid_total", "change_given",
            "status", "edit_deadline_at",
            "client_uuid", "notes", "is_held", "held_label",
            "items", "payments",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "local_invoice_number",
            "fbr_invoice_number", "fbr_qr_payload",
            "fbr_submitted_at", "fbr_validated_at",
            "subtotal", "discount_total", "tax_total", "grand_total",
            "paid_total", "change_given", "edit_deadline_at",
            "items", "payments", "created_at", "updated_at",
        )


class CheckoutLineSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=4)
    discount_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    discount_amount = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, default=0,
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    is_taxable = serializers.BooleanField(default=True)


class CheckoutPaymentSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=["cash", "card_credit", "card_debit", "easypaisa", "jazzcash",
                 "raast", "bank_transfer", "store_credit", "cheque"],
    )
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)


class CheckoutSerializer(serializers.Serializer):
    """Body of POST /api/sales/invoices/checkout/."""
    branch = serializers.UUIDField()
    terminal = serializers.UUIDField()
    cash_session = serializers.UUIDField(required=False, allow_null=True)
    customer = serializers.UUIDField(required=False, allow_null=True)
    cart_lines = CheckoutLineSerializer(many=True)
    cart_discount_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    payments = CheckoutPaymentSerializer(many=True)
    client_uuid = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class HoldSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=50)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=2, max_length=500)


class SessionOpenSerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    terminal = serializers.UUIDField()
    opening_amount = serializers.DecimalField(max_digits=14, decimal_places=4)


class SessionCloseSerializer(serializers.Serializer):
    declared_amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    variance_reason = serializers.CharField(required=False, allow_blank=True, default="")
