"""Platform / control-plane models.

Reserved Phase-0-stub of the future platform app per the project plan
(SUPER_ADMIN.md sections 3.1–3.5). The full Phase 9 build adds billing,
support tickets, impersonation, analytics — explicitly NOT here. This
file is just the data foundation so we can manually onboard the first
~10 customers without schema churn later.

Field names match SUPER_ADMIN.md exactly so Phase 9 can extend without
renames.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.models import TimestampedModel
from core.uuid7 import uuid7


# ---------------------------------------------------------------------------
# PlatformSettings (singleton)
# ---------------------------------------------------------------------------


class PlatformSettings(TimestampedModel):
    """Singleton row holding platform-wide config the founder/platform-team
    edits via Django admin. Enforced as singleton at the app layer (admin
    refuses a second row); Phase 9 may switch to a dedicated migration
    constraint.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    platform_name = models.CharField(
        max_length=100, default="Pakistan POS",
        help_text="Brand name shown on customer-facing surfaces.",
    )
    support_email = models.EmailField(blank=True, default="")
    support_phone = models.CharField(max_length=30, blank=True, default="")

    # Default trial length for new self-service signups (days).
    default_trial_days = models.PositiveIntegerField(default=14)

    # Bank / wallet details for receiving customer payments. The
    # platform is run from Pakistan; no Stripe — all bank transfer +
    # JazzCash Business + EasyPaisa Business + Raast.
    payment_bank_name = models.CharField(max_length=100, blank=True, default="")
    payment_bank_account_title = models.CharField(max_length=255, blank=True, default="")
    payment_bank_iban = models.CharField(max_length=50, blank=True, default="")
    payment_jazzcash_business = models.CharField(max_length=20, blank=True, default="")
    payment_easypaisa_business = models.CharField(max_length=20, blank=True, default="")
    payment_raast_id = models.CharField(max_length=50, blank=True, default="")

    # Maintenance toggle (Phase 9 wires the actual middleware response;
    # we just hold the flag here in the stub).
    maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "platform_settings"
        verbose_name = "Platform settings"
        verbose_name_plural = "Platform settings"

    def __str__(self) -> str:
        return self.platform_name

    @classmethod
    def load(cls) -> "PlatformSettings":
        """Get-or-create the singleton row."""
        obj, _ = cls.objects.get_or_create()
        return obj


# ---------------------------------------------------------------------------
# SubscriptionPlan
# ---------------------------------------------------------------------------


BILLING_CYCLES = (
    ("monthly", "Monthly"),
    ("yearly", "Yearly"),
)


class SubscriptionPlan(TimestampedModel):
    """A pricing tier the platform offers. Three default rows seeded
    (Starter, Pro, Enterprise) per SUPER_ADMIN.md section 5; editable via
    Django admin during V1 to learn what works.

    Money is BIGINT paisa (1 PKR = 100 paisa) per SUPER_ADMIN.md
    section 3 to avoid Decimal vs float drift on the platform side.
    Tenant-side FBR invoices stay Decimal(14,4) per CLAUDE.md.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    code = models.CharField(
        max_length=50, unique=True,
        help_text="Stable identifier (e.g. 'starter', 'pro', 'enterprise').",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")

    # Prices in paisa.
    monthly_price_paisa = models.BigIntegerField(default=0)
    yearly_price_paisa = models.BigIntegerField(default=0)

    # Limits — `None` (NULL) = unlimited.
    max_branches = models.PositiveIntegerField(blank=True, null=True)
    max_terminals = models.PositiveIntegerField(blank=True, null=True)
    max_products = models.PositiveIntegerField(blank=True, null=True)
    max_users = models.PositiveIntegerField(blank=True, null=True)

    # Feature flags. Phase 9 may move these into a separate FeatureFlag
    # model with per-tenant overrides; for now a JSON blob is enough.
    features = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True, help_text="Hide from new signups when false.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "subscription_plans"
        ordering = ("sort_order", "monthly_price_paisa")

    def __str__(self) -> str:
        return self.name

    @property
    def monthly_price_rs(self) -> Decimal:
        return Decimal(self.monthly_price_paisa) / Decimal(100)

    @property
    def yearly_price_rs(self) -> Decimal:
        return Decimal(self.yearly_price_paisa) / Decimal(100)


# ---------------------------------------------------------------------------
# Subscription — links Tenant to a Plan
# ---------------------------------------------------------------------------


SUBSCRIPTION_STATUS_CHOICES = (
    ("trial", "Trial"),
    ("active", "Active"),
    ("past_due", "Past due"),
    ("suspended", "Suspended"),
    ("cancelled", "Cancelled"),
)


class Subscription(TimestampedModel):
    """One Subscription per Tenant (current). When a tenant changes plan,
    we update this row in place rather than creating multi-row history;
    Phase 9 adds the dedicated history table.

    Phase 0 stub fields only — no add-ons, pro-ration, discounts, or
    cancel_at_period_end yet (those land in Phase 9).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    status = models.CharField(
        max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, default="trial",
    )
    billing_cycle = models.CharField(
        max_length=10, choices=BILLING_CYCLES, default="monthly",
    )

    # Trial / billing dates.
    trial_started_at = models.DateTimeField(blank=True, null=True)
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    current_period_start = models.DateTimeField(blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)
    next_invoice_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "subscriptions"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["next_invoice_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.business_name} · {self.plan.code} ({self.status})"
