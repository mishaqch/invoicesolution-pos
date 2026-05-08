"""Payments API serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.sales.models import Payment
from apps.tenants.models import TenantSettings


class TenantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSettings
        fields = (
            "enabled_payment_methods",
            "easypaisa_merchant_id", "easypaisa_qr_url",
            "jazzcash_merchant_id", "jazzcash_qr_url",
            "raast_iban", "raast_qr_url",
            "bank_account_name", "bank_account_iban", "bank_account_bank",
            "updated_at",
        )
        read_only_fields = ("updated_at",)


class PaymentMethodConfigSerializer(serializers.Serializer):
    """Subset shipped to the POS — what the cashier needs to render sub-flows."""
    enabled_payment_methods = serializers.ListField(child=serializers.CharField())
    easypaisa_qr_url = serializers.CharField(allow_blank=True)
    jazzcash_qr_url = serializers.CharField(allow_blank=True)
    raast_qr_url = serializers.CharField(allow_blank=True)
    raast_iban = serializers.CharField(allow_blank=True)
    bank_account_name = serializers.CharField(allow_blank=True)
    bank_account_iban = serializers.CharField(allow_blank=True)
    bank_account_bank = serializers.CharField(allow_blank=True)


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
        read_only_fields = fields


class ChequeBouncedSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
