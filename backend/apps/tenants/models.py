"""Tenant + TenantMembership models.

Field-by-field mapping to DATABASE_SCHEMA.md §1. Deviations from the raw SQL
are noted inline.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.tenants.managers import TenantScopedManager
from apps.tenants.modules import default_modules_enabled as _default_modules_enabled
from core.uuid7 import uuid7

# ---------------------------------------------------------------------------
# Enums (kept as module-level tuples so we can also reference them in CHECK
# constraints via migrations; choices=… on the field gives us form validation
# for free.)
# ---------------------------------------------------------------------------

BUSINESS_TYPES = (
    ("sole_proprietor", "Sole Proprietor"),
    ("partnership", "Partnership"),
    ("private_ltd", "Private Limited"),
    ("public_ltd", "Public Limited"),
    ("aop", "Association of Persons"),
)

PROVINCES = (
    ("PUNJAB", "Punjab"),
    ("SINDH", "Sindh"),
    ("KP", "Khyber Pakhtunkhwa"),
    ("BALOCHISTAN", "Balochistan"),
    ("ICT", "Islamabad Capital Territory"),
    ("GB", "Gilgit-Baltistan"),
    ("AJK", "Azad Jammu & Kashmir"),
)

SUBSCRIPTION_PLANS = (
    ("starter", "Starter"),
    ("pro", "Pro"),
    ("enterprise", "Enterprise"),
)

SUBSCRIPTION_STATUSES = (
    ("trial", "Trial"),
    ("active", "Active"),
    ("past_due", "Past due"),
    ("suspended", "Suspended"),
    ("cancelled", "Cancelled"),
)

ROLES = (
    ("owner", "Owner"),
    ("manager", "Manager"),
    ("cashier", "Cashier"),
    ("accountant", "Accountant"),
    ("auditor", "Auditor"),
)


class Tenant(models.Model):
    """The business that has subscribed to our POS.

    Tenant has no `tenant` FK (it IS the tenant) so it inherits from plain
    Model + manual timestamp fields rather than TenantScopedModel.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    business_name = models.CharField(max_length=255)
    ntn = models.CharField(max_length=20, unique=True)
    strn = models.CharField(max_length=20, blank=True, null=True)
    cnic_owner = models.CharField(max_length=15, blank=True, null=True)

    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES)
    fbr_business_natures = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
    )
    fbr_sector = models.CharField(max_length=50, blank=True, null=True)
    province = models.CharField(max_length=20, choices=PROVINCES)

    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    logo_url = models.TextField(blank=True, null=True)

    subscription_plan = models.CharField(
        max_length=50, choices=SUBSCRIPTION_PLANS, default="starter"
    )
    subscription_status = models.CharField(
        max_length=20, choices=SUBSCRIPTION_STATUSES, default="trial"
    )
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    next_billing_at = models.DateTimeField(blank=True, null=True)

    # Phase 0 platform stub — control-plane fields. Authoritative plan
    # + billing state lives on platform_admin.Subscription (one-to-one
    # via tenant.subscription); the legacy plan/status chars above remain
    # for backwards compatibility, deprecated in Phase 9.
    signup_source = models.CharField(
        max_length=50, blank=True, default="",
        help_text="How did this tenant arrive? e.g. self_serve, sales, "
                  "reseller, partner_referral.",
    )
    account_manager = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="managed_tenants",
        help_text="Platform staff member responsible for this tenant.",
    )
    suspended_at = models.DateTimeField(blank=True, null=True)
    internal_notes = models.TextField(
        blank=True, default="",
        help_text="Platform-team-only notes about this tenant.",
    )
    tags = models.JSONField(
        default=list, blank=True,
        help_text="Free-form list of tags (e.g. ['vip', 'cash-only']).",
    )

    # Phase 8 — first-run onboarding wizard progress (free-form; the admin
    # web reads keys like `profile_done`, `branch_done`, `terminal_done`,
    # `product_done`, `first_sale_done`, `dismissed_at`).
    onboarding_state = models.JSONField(default=dict, blank=True)

    # Per-tenant module gates set by super-admin. Stored as a JSON array
    # of module keys (e.g. ["sales", "fbr", "customers", "branches"]).
    # The catalog lives in apps.tenants.modules.MODULES; forced modules
    # like "sales" and "fbr" are always honored regardless of what's in
    # this list. Default for new tenants (and the migration backfill) is
    # everything-enabled, so super-admin opts OUT of modules rather than
    # opting in — protects against new tenants accidentally landing with
    # zero modules and being unable to do anything.
    modules_enabled = models.JSONField(
        default=_default_modules_enabled, blank=True,
        help_text="Module keys this tenant is allowed to use. Forced "
                  "modules (sales, fbr) are always enabled. Edit via "
                  "the 'Modules enabled' widget on the change form.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants"

    def __str__(self) -> str:
        return self.business_name


class TenantMembership(models.Model):
    """Which user belongs to which tenant, in what role."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=30, choices=ROLES)

    # Schema says UUID[]; empty list means "all branches".
    branch_ids = ArrayField(models.UUIDField(), default=list, blank=True)

    is_active = models.BooleanField(default=True)
    custom_permissions = models.JSONField(default=dict, blank=True)

    invited_at = models.DateTimeField(blank=True, null=True)
    joined_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                name="uniq_tenant_user_membership",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_memberships_user"),
            models.Index(
                fields=["tenant"],
                name="idx_memberships_tenant_active",
                condition=models.Q(is_active=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} → {self.tenant_id} ({self.role})"


# ---------------------------------------------------------------------------
# Locations & devices (DATABASE_SCHEMA.md §2)
# ---------------------------------------------------------------------------


class Branch(models.Model):
    """A physical outlet."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="branches",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=20, choices=PROVINCES)
    phone = models.CharField(max_length=20, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    fbr_pos_id = models.CharField(max_length=50, blank=True, null=True)

    receipt_header = models.TextField(blank=True, null=True)
    receipt_footer = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "branches"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uniq_branch_tenant_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant"],
                name="idx_branches_tenant",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Terminal(models.Model):
    """A POS terminal device. Each Electron install registers as one."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="terminals",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="terminals",
    )
    name = models.CharField(max_length=100)
    device_fingerprint = models.CharField(max_length=128, unique=True)
    os_version = models.CharField(max_length=50, blank=True, null=True)
    app_version = models.CharField(max_length=20, blank=True, null=True)

    printer_config = models.JSONField(default=dict, blank=True)
    scanner_config = models.JSONField(default=dict, blank=True)
    drawer_config = models.JSONField(default=dict, blank=True)
    customer_display_enabled = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "terminals"
        indexes = [
            models.Index(
                fields=["branch"],
                name="idx_terminals_branch",
                condition=models.Q(is_active=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} @ {self.branch_id}"


class CashSession(models.Model):
    """A day-open / day-close cycle. One per terminal at a time per the
    `idx_cash_sessions_terminal_open` partial uniqueness rule.

    Tracking lives on the cash_sessions row; the actual cash math runs in
    apps/sales/services/sessions.py. Money in DECIMAL(14,4).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="cash_sessions"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="cash_sessions"
    )
    terminal = models.ForeignKey(
        Terminal, on_delete=models.PROTECT, related_name="cash_sessions"
    )
    cashier = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="cash_sessions"
    )

    opened_at = models.DateTimeField()
    opened_with_amount = models.DecimalField(max_digits=14, decimal_places=4)
    closed_at = models.DateTimeField(blank=True, null=True)
    closed_with_amount = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    expected_amount = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    variance = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    variance_reason = models.TextField(blank=True, default="")

    total_sales = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    total_returns = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cash_in = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cash_out = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    status = models.CharField(
        max_length=20,
        choices=(("open", "Open"), ("closed", "Closed")),
        default="open",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "cash_sessions"
        indexes = [
            models.Index(
                fields=["terminal"], name="idx_cash_sessions_term_open",
                condition=models.Q(status="open"),
            ),
            models.Index(
                fields=["tenant", "-opened_at"],
                name="idx_cash_sessions_tenant_date",
            ),
        ]
        constraints = [
            # At most one open session per terminal.
            models.UniqueConstraint(
                fields=["terminal"], condition=models.Q(status="open"),
                name="uniq_open_session_per_terminal",
            ),
        ]

    def __str__(self) -> str:
        return f"CashSession {self.terminal_id} {self.opened_at:%Y-%m-%d}"


# ---------------------------------------------------------------------------
# Per-tenant settings (DATABASE_SCHEMA.md §11). Phase 5 ships the payment-
# relevant subset; receipt/FBR/notification subsets land in Phase 8 polish.
# ---------------------------------------------------------------------------


PAYMENT_METHODS = (
    "cash",
    "card_credit",
    "card_debit",
    "easypaisa",
    "jazzcash",
    "raast",
    "bank_transfer",
    "store_credit",
    "cheque",
)


class TenantSettings(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="settings",
    )

    # Payment config
    enabled_payment_methods = ArrayField(
        models.CharField(max_length=30),
        default=list,
        blank=True,
    )

    easypaisa_merchant_id = models.CharField(max_length=50, blank=True, default="")
    easypaisa_qr_url = models.TextField(blank=True, default="")

    jazzcash_merchant_id = models.CharField(max_length=50, blank=True, default="")
    jazzcash_qr_url = models.TextField(blank=True, default="")

    raast_iban = models.CharField(max_length=34, blank=True, default="")
    raast_qr_url = models.TextField(blank=True, default="")

    bank_account_name = models.CharField(max_length=100, blank=True, default="")
    bank_account_iban = models.CharField(max_length=34, blank=True, default="")
    bank_account_bank = models.CharField(max_length=50, blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "tenant_settings"

    def __str__(self) -> str:
        return f"Settings {self.tenant_id}"
