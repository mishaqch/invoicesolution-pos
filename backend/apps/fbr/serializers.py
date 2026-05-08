"""FBR API serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    FbrCancelBudget,
    FbrCancelBudgetConsumption,
    FbrIpWhitelist,
    FbrScenarioTest,
    FbrSubmission,
    FbrToken,
)


class FbrTokenSerializer(serializers.ModelSerializer):
    """Never serialize the token plaintext."""
    has_token = serializers.SerializerMethodField()

    class Meta:
        model = FbrToken
        fields = (
            "id", "environment", "licensed_integrator",
            "api_endpoint", "is_active", "activated_at", "expires_at",
            "has_token", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_has_token(self, obj: FbrToken) -> bool:
        return bool(obj.token_encrypted)


class FbrSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FbrSubmission
        fields = (
            "id", "invoice", "environment", "endpoint",
            "request_payload", "response_payload",
            "http_status", "status_code", "fbr_invoice_number",
            "attempt_number", "duration_ms", "error_message",
            "submitted_at",
        )
        read_only_fields = fields


class FbrScenarioTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = FbrScenarioTest
        fields = (
            "id", "scenario_code", "scenario_description", "status",
            "fbr_invoice_number", "last_attempt_at", "error_message",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class FbrCancelBudgetConsumptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FbrCancelBudgetConsumption
        fields = (
            "id", "invoice", "consumption_type", "amount",
            "consumed_at", "consumed_by",
        )
        read_only_fields = fields


class FbrCancelBudgetSerializer(serializers.ModelSerializer):
    consumptions = FbrCancelBudgetConsumptionSerializer(many=True, read_only=True)

    class Meta:
        model = FbrCancelBudget
        fields = (
            "id", "month_start", "previous_month_sales",
            "budget_amount", "consumed_amount", "remaining_amount",
            "last_recalculated_at", "consumptions",
        )
        read_only_fields = fields


class FbrIpWhitelistSerializer(serializers.ModelSerializer):
    class Meta:
        model = FbrIpWhitelist
        fields = (
            "id", "tenant", "ip_address", "hosting_provider",
            "hosting_country", "status", "approved_at", "notes", "created_at",
        )
        read_only_fields = ("id", "created_at")


# ---------------------------------------------------------------------------
# Onboarding wizard
# ---------------------------------------------------------------------------


class TokenSubmitSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=10, max_length=500)
    api_endpoint = serializers.CharField(
        required=False, default="https://gw.fbr.gov.pk",
    )


class CancelInvoiceSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=2, max_length=500)
