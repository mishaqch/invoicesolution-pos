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


class BranchFbrToken(TenantScopedModel):
    """Per-branch FBR token for POS.

    Unlike `FbrToken` (one bearer per tenant, used by Digital Invoicing),
    each registered POS outlet has its OWN FBR credentials: POS ID + Code
    (stored on Branch) and a distinct bearer token (here). A tenant with
    several POS branches therefore has several tokens — one per branch —
    and each branch's sales must be submitted with its own bearer.

    POS registration on FBR issues the production token directly (no sandbox /
    scenario testing for POS), so these are production tokens. The submission
    path prefers a branch token when the invoice's branch has an active one,
    and falls back to the tenant-level FbrToken otherwise (the Digital
    Invoicing path — left untouched).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    branch = models.ForeignKey(
        "tenants.Branch", on_delete=models.CASCADE,
        related_name="fbr_tokens",
    )
    environment = models.CharField(
        max_length=20, choices=ENVIRONMENTS, default="production",
    )
    licensed_integrator = models.CharField(max_length=50, default="PRAL")
    token_encrypted = models.TextField(db_column="token_encrypted")
    api_endpoint = models.TextField(default="https://gw.fbr.gov.pk")
    is_active = models.BooleanField(default=True)
    activated_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "branch_fbr_tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "environment"],
                name="uniq_branch_fbr_token_branch_env",
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
        return f"branch={self.branch_id} {self.environment}"


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
    # IRIS assigned this scenario to the tenant but our platform
    # doesn't ship a payload-builder for it yet. The runner skips
    # without contacting PRAL; the UI shows "Not yet supported".
    ("not_implemented", "Not yet supported"),
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


# ---------------------------------------------------------------------------
# Scenario payload templates (platform-level, not tenant-scoped)
# ---------------------------------------------------------------------------
#
# When a super-admin gets a scenario working for one tenant (after the
# typical 2–5 round PRAL iteration), they save the working payload as
# a TEMPLATE. The next time a tenant of the same business type is
# onboarded, they apply the template pack — all scenario payloads
# are pre-seeded with PRAL-verified field values.
#
# Templates store the seller-specific fields (NTN, province, address)
# as placeholder tokens so applying the template to a new tenant
# substitutes the new tenant's seller values automatically. The
# operator-facing "{{seller.ntn}}", "{{seller.business_name}}",
# "{{seller.province}}", "{{seller.address}}" tokens get replaced at
# apply-time; everything else (saleType, sroScheduleNo, rate, amounts)
# is reused verbatim.
#
# Templates are platform-level: only super-admin can create or edit;
# any tenant in the catalog can apply them.


class ScenarioPayloadTemplate(models.Model):
    """Reusable PRAL payload template for a single scenarioId.

    Lifecycle:
      1. Super-admin gets scenario SN001 working for tenant A.
      2. They click "Save as template" on the card → row created here
         with the payload (placeholders substituted).
      3. Onboarding tenant B (same business type), super-admin clicks
         "Apply template pack" → for each template matching tenant B's
         assigned scenarios, payload is materialised against tenant B's
         seller block and stored in a per-tenant override field.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    # Free-text identifier shown in dropdowns. Recommended convention:
    # "Wholesaler/Retailer — SN001" so super-admin can scan templates
    # by business type + scenario.
    name = models.CharField(max_length=255)

    scenario_code = models.CharField(max_length=10)  # e.g. "SN001"

    # JSON payload with seller-specific fields tokenised. Stored as-is;
    # tokenisation is performed at template-save time, substitution at
    # apply-time. See apps/fbr/services.py:apply_template.
    payload = models.JSONField()

    # Free-form text for super-admin notes — typically "what PRAL
    # rejected / what the fix was" so future operators know the
    # rationale behind each field choice.
    notes = models.TextField(blank=True, default="")

    # Bookkeeping
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="created_scenario_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fbr_scenario_payload_templates"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "scenario_code"],
                name="uniq_scenario_template_name_code",
            ),
        ]
        indexes = [
            models.Index(fields=["scenario_code"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} · {self.scenario_code}"

