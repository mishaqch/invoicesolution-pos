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
    """Never serialize the token plaintext.

    `token_preview` returns a Stripe-style masked form ("865acb97…b0a9")
    so the operator can confirm which token is configured without
    seeing the bearer. The server itself can decrypt the full token
    (that's how PRAL calls work), but the UI never receives it.
    """
    has_token = serializers.SerializerMethodField()
    token_preview = serializers.SerializerMethodField()

    class Meta:
        model = FbrToken
        fields = (
            "id", "environment", "licensed_integrator",
            "api_endpoint", "is_active", "activated_at", "expires_at",
            "has_token", "token_preview",
            "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_has_token(self, obj: FbrToken) -> bool:
        return bool(obj.token_encrypted)

    def get_token_preview(self, obj: FbrToken) -> str | None:
        if not obj.token_encrypted:
            return None
        try:
            raw = obj.token
        except Exception:
            return None
        if not raw or len(raw) < 8:
            return "•" * len(raw or "")
        # Show first 4 + last 4 characters joined by an ellipsis. Same
        # pattern Stripe, GitHub, and AWS use for secret previews.
        return f"{raw[:4]}…{raw[-4:]}"


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
    # The most-recent submission attached to this scenario_code is
    # surfaced inline so the UI's "Show request/response" inspector
    # can render what we sent + what PRAL returned, without needing
    # a separate API call to /api/fbr/submissions/.
    last_request_payload = serializers.SerializerMethodField()
    last_response_payload = serializers.SerializerMethodField()

    class Meta:
        model = FbrScenarioTest
        fields = (
            "id", "scenario_code", "scenario_description", "status",
            "fbr_invoice_number", "last_attempt_at", "error_message",
            "last_request_payload", "last_response_payload",
            "created_at", "updated_at",
        )
        read_only_fields = fields

    def _last_submission(self, obj: FbrScenarioTest):
        """Find the most recent FbrSubmission whose request_payload's
        scenarioId matches this row. We don't have a FK from
        FbrSubmission → FbrScenarioTest (scenarios share the same
        tenant + invoice-less submission rows), so we look up by
        scenarioId field on the payload JSON.

        Uses a JSON path lookup that Postgres handles natively. Cached
        on the instance so list-views don't re-query for every card.
        """
        cached = getattr(obj, "_cached_last_submission", "__unset__")
        if cached != "__unset__":
            return cached
        sub = (
            FbrSubmission.objects.filter(
                tenant_id=obj.tenant_id,
                environment="sandbox",
                endpoint="postinvoicedata",
                request_payload__scenarioId=obj.scenario_code,
            )
            .order_by("-submitted_at")
            .first()
        )
        obj._cached_last_submission = sub
        return sub

    def get_last_request_payload(self, obj: FbrScenarioTest):
        sub = self._last_submission(obj)
        return sub.request_payload if sub else None

    def get_last_response_payload(self, obj: FbrScenarioTest):
        sub = self._last_submission(obj)
        return sub.response_payload if sub else None


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
    # token is optional so an operator can update JUST the endpoint
    # without re-pasting the bearer (which they don't have anymore —
    # we only stored the encrypted form). When token is empty, the
    # view treats it as "keep the existing token, update endpoint".
    # When token is provided it must still be >= 10 chars to catch
    # obvious typos.
    token = serializers.CharField(
        required=False, allow_blank=True, max_length=500,
    )
    api_endpoint = serializers.CharField(
        required=False, default="https://gw.fbr.gov.pk",
    )
    # Platform-admin-only escape hatch: activate a production token that FBR
    # already issued (i.e. sandbox scenarios were cleared on the FBR portal /
    # via the IMS), without requiring our own scenario runner to be green. The
    # VIEW enforces that only platform staff may set this to true.
    scenarios_cleared_externally = serializers.BooleanField(
        required=False, default=False,
    )

    def validate_token(self, value):
        if value and len(value) < 10:
            raise serializers.ValidationError(
                "Token looks too short (under 10 chars). Paste the full "
                "bearer string PRAL gave you, or leave blank to keep the "
                "existing token."
            )
        return value


class BranchTokenSubmitSerializer(serializers.Serializer):
    """Set/update a single branch's FBR POS token. No scenario gate — POS
    registrations get a production token directly from FBR."""

    branch_id = serializers.UUIDField()
    token = serializers.CharField(required=False, allow_blank=True, max_length=500)
    api_endpoint = serializers.CharField(
        required=False, default="https://gw.fbr.gov.pk",
    )

    def validate_token(self, value):
        if value and len(value) < 10:
            raise serializers.ValidationError(
                "Token looks too short (under 10 chars). Paste the full "
                "bearer FBR gave you for this POS, or leave blank to keep "
                "the existing one."
            )
        return value


class BranchFbrTokenSerializer(serializers.Serializer):
    """Read-only view of a branch's stored token (never exposes the secret)."""

    branch_id = serializers.UUIDField()
    environment = serializers.CharField()
    api_endpoint = serializers.CharField()
    is_active = serializers.BooleanField()
    has_token = serializers.SerializerMethodField()
    token_preview = serializers.SerializerMethodField()
    activated_at = serializers.DateTimeField()

    def get_has_token(self, obj) -> bool:
        return bool(obj.token_encrypted)

    def get_token_preview(self, obj) -> str | None:
        if not obj.token_encrypted:
            return None
        try:
            raw = obj.token
        except Exception:
            return None
        if len(raw) <= 12:
            return "…"
        return f"{raw[:8]}…{raw[-4:]}"


class CancelInvoiceSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=2, max_length=500)
