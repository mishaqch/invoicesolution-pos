"""FBR / PRAL models per DATABASE_SCHEMA.md §9.

Tokens are encrypted at rest via the `_token_encrypted` column; the public
`token` property handles encrypt-on-set / decrypt-on-get. A test verifies
a raw DB dump never contains plaintext.

`fbr_submissions` is append-only — REVOKE UPDATE, DELETE in migration 0002.
The `invoices.fbr_invoice_number` immutability trigger is also in 0002.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7

from .encryption import decrypt, encrypt


ENVIRONMENTS = (
    ("sandbox", "Sandbox"),
    ("production", "Production"),
)


class FbrToken(TenantScopedModel):
    """Sandbox + production tokens per tenant. Stored encrypted at rest."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    environment = models.CharField(max_length=20, choices=ENVIRONMENTS)
    licensed_integrator = models.CharField(max_length=50, default="PRAL")

    # The actual ciphertext; never expose. Use `token` property.
    token_encrypted = models.TextField(db_column="token_encrypted")

    api_endpoint = models.TextField()

    is_active = models.BooleanField(default=True)
    activated_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "fbr_tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment"],
                name="uniq_fbr_token_tenant_env",
            ),
        ]

    @property
    def token(self) -> str:
        return decrypt(self.token_encrypted)

    @token.setter
    def token(self, value: str) -> None:
        self.token_encrypted = encrypt(value)

    def set_token(self, raw: str) -> None:
        self.token = raw

    def __str__(self) -> str:
        return f"{self.tenant_id} {self.environment}"


SUBMISSION_ENDPOINTS = (
    ("postinvoicedata", "postinvoicedata"),
    ("validateinvoicedata", "validateinvoicedata"),
    ("editinvoice", "editinvoice"),
    ("cancelinvoice", "cancelinvoice"),
)


class FbrSubmission(TenantScopedModel):
    """Append-only log of every PRAL API call.

    REVOKE UPDATE, DELETE applied at the DB level in migration 0002.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    invoice = models.ForeignKey(
        "sales.Invoice", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="fbr_submissions",
    )
    # `return_id` foreign-key is reserved for Phase 6; storing as nullable UUID
    # for now avoids a model dependency on a not-yet-existing app.
    return_ref = models.UUIDField(blank=True, null=True)

    environment = models.CharField(max_length=20, choices=ENVIRONMENTS)
    endpoint = models.CharField(max_length=100, choices=SUBMISSION_ENDPOINTS)

    request_payload = models.JSONField()
    response_payload = models.JSONField(blank=True, null=True)

    http_status = models.IntegerField(blank=True, null=True)
    status_code = models.CharField(max_length=20, blank=True, null=True)
    fbr_invoice_number = models.CharField(max_length=40, blank=True, null=True)

    attempt_number = models.IntegerField(default=1)
    duration_ms = models.IntegerField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fbr_submissions"
        indexes = [
            models.Index(
                fields=["invoice", "-submitted_at"],
                name="idx_fbr_submissions_invoice",
            ),
            models.Index(
                fields=["tenant", "-submitted_at"],
                name="idx_fbr_subs_failed",
                condition=~models.Q(status_code="00"),
            ),
        ]


SCENARIO_STATUSES = (
    ("pending", "Pending"),
    ("submitting", "Submitting"),
    ("success", "Success"),
    ("failed", "Failed"),
)


class FbrScenarioTest(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    scenario_code = models.CharField(max_length=10)
    scenario_description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=SCENARIO_STATUSES, default="pending")
    fbr_invoice_number = models.CharField(max_length=40, blank=True, null=True)
    last_attempt_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "fbr_scenario_tests"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "scenario_code"],
                name="uniq_fbr_scenario_tenant_code",
            ),
        ]


class FbrCancelBudget(TenantScopedModel):
    """The 10% monthly cap. One row per tenant per month.

    Atomic consume goes through services.consume_cancel_budget — uses
    select_for_update on this row so concurrent attempts serialize.
    """
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    month_start = models.DateField()  # always the 1st of a month, PKT
    previous_month_sales = models.DecimalField(max_digits=14, decimal_places=4)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=4)
    consumed_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    remaining_amount = models.DecimalField(max_digits=14, decimal_places=4)
    last_recalculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fbr_cancel_budget"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "month_start"],
                name="uniq_fbr_budget_tenant_month",
            ),
        ]


CONSUMPTION_TYPES = (
    ("edit", "Edit"),
    ("cancel", "Cancel"),
)


class FbrCancelBudgetConsumption(models.Model):
    """One row per cancel/edit that ate budget. Inherits tenant via the budget."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    budget = models.ForeignKey(
        FbrCancelBudget, on_delete=models.PROTECT,
        related_name="consumptions",
    )
    invoice = models.ForeignKey(
        "sales.Invoice", on_delete=models.PROTECT,
        related_name="cancel_budget_consumptions",
    )
    consumption_type = models.CharField(max_length=20, choices=CONSUMPTION_TYPES)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    consumed_at = models.DateTimeField(auto_now_add=True)
    consumed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
    )

    class Meta:
        db_table = "fbr_cancel_budget_consumption"
        indexes = [
            models.Index(fields=["budget"], name="idx_consumption_budget"),
        ]


IP_STATUSES = (
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
)


class FbrIpWhitelist(models.Model):
    """Static IPs we declare to PRAL. NULL tenant = global infra IP."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE,
        blank=True, null=True, related_name="fbr_ip_whitelist_entries",
    )
    ip_address = models.GenericIPAddressField()
    hosting_provider = models.CharField(max_length=100, blank=True, default="")
    hosting_country = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(max_length=20, choices=IP_STATUSES, default="pending")
    approved_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fbr_ip_whitelist"
