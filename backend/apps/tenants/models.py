"""Tenant + TenantMembership models.

Field-by-field mapping to DATABASE_SCHEMA.md §1. Deviations from the raw SQL
are noted inline.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.tenants.business_mode import (
    BUSINESS_MODES,
    DEFAULT_BUSINESS_MODE,
    FBR_BUSINESS_NATURE_CHOICES,
    FBR_SECTOR_CHOICES,
)
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

    # Product mode — POS vs Digital Invoicing vs both. Drives which
    # modules are unlocked by default at onboarding and how the
    # frontend chrome is rendered. Editable post-onboarding via the
    # admin's setup wizard; flipping it does NOT auto-toggle modules
    # (super-admin owns module config), only the initial wizard does.
    business_mode = models.CharField(
        max_length=20, choices=BUSINESS_MODES, default=DEFAULT_BUSINESS_MODE,
    )

    # FBR-defined taxonomy. Wire values are the exact strings PRAL
    # accepts. Mis-spelling these on submission causes hard-to-debug
    # invoice rejections, so we constrain via choices.
    fbr_business_natures = ArrayField(
        models.CharField(max_length=50, choices=FBR_BUSINESS_NATURE_CHOICES),
        default=list,
        blank=True,
        help_text="One or more FBR-defined business natures. Required "
                  "before submitting invoices to PRAL.",
    )
    fbr_sector = models.CharField(
        max_length=50, choices=FBR_SECTOR_CHOICES, blank=True, null=True,
        help_text="The single FBR-defined sector this tenant operates "
                  "in. Drives the scenarioId list for sandbox testing.",
    )

    # Per-tenant FBR scenario assignment from IRIS.
    #
    # Background: PRAL assigns each Digital Invoicing tenant a SPECIFIC
    # list of scenarios they must pass in sandbox before production
    # activation. The list is visible to the tenant on their IRIS
    # profile page (Adnan Jamil's wholesaler/retailer profile, for
    # instance, lists SN001, SN002, SN008, SN026, SN027, SN028). PRAL
    # does NOT expose this list via API — we tried every plausible
    # endpoint and got 404. So the super-admin must paste it from IRIS.
    #
    # When set, this list overrides the nature×sector mapping in
    # apps/fbr/scenarios.py:ELIGIBLE_BY_NATURE_AND_SECTOR. When empty,
    # we fall back to the table so existing tenants keep working
    # without operator intervention.
    #
    # Stored as a JSON array of scenario codes: ["SN001", "SN002", ...].
    # Codes are validated against apps.fbr.scenarios.SCENARIOS at the
    # form layer, not the DB level, because the scenario catalog is
    # code-driven (registered via @register decorator).
    assigned_scenarios = models.JSONField(
        default=list, blank=True,
        help_text="The FBR scenarios assigned to this tenant in IRIS. "
                  "Paste from the tenant's IRIS profile. When set, this "
                  "list determines which scenarios the runner tests "
                  "(overrides our manual-derived nature×sector default).",
    )

    # NTN of a real registered buyer that PRAL has on file, used by
    # registered-buyer scenario tests (SN001, SN005). PRAL's documented
    # test NTN "1000000000007" is NOT actually registered in their
    # sandbox database — every registered-buyer scenario fails with
    # errorCode 0205 ("Provided scenario not valid for unregistered
    # user") unless we send a real NTN.
    #
    # Operator must arrange this with a partner business (any company
    # with valid FBR/IRIS registration who allows their NTN to be used
    # for sandbox testing). 13 digits. Leave empty if the tenant has
    # no registered-buyer scenarios in their IRIS list.
    fbr_test_buyer_ntn = models.CharField(
        max_length=20, blank=True, default="",
        help_text="NTN of a real registered buyer for sandbox SN001/SN005 "
                  "tests. PRAL's docs default (1000000000007) is not "
                  "actually registered — arrange a real NTN with a "
                  "partner business. Leave empty if no registered-"
                  "buyer scenarios are assigned.",
    )
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

    # ------------------------------------------------------------------
    # Safe-edit guard — same shape as User.tenants_where_last_active_owner.
    #
    # Three operations can orphan a tenant by mutating an existing
    # membership (not just deleting a user):
    #   1. Toggle is_active False on the only active owner
    #   2. Change role owner → cashier on the only active owner
    #   3. Direct DELETE of the only active owner membership row
    #
    # We refuse all three at the model layer so admin form, Django
    # shell, and any future tenant-API endpoint that lets owners
    # manage memberships all hit the same gate.
    # ------------------------------------------------------------------

    def _is_contributing_active_owner_now(self) -> bool:
        """Does THIS row currently (in the DB, pre-save) count as an
        active owner of its tenant? New rows return False since there
        is no DB state yet to contribute."""
        if not self.pk:
            return False
        try:
            db_row = TenantMembership.objects.only(
                "role", "is_active", "tenant_id",
            ).get(pk=self.pk)
        except TenantMembership.DoesNotExist:
            return False
        return db_row.role == "owner" and db_row.is_active

    def _would_be_active_owner_after_save(self) -> bool:
        """Will THIS row count as an active owner after the in-memory
        values are saved? Used together with the pre-save check to
        detect 'this row is about to stop being an active owner'."""
        return self.role == "owner" and self.is_active

    def _tenant_has_other_active_owner(self) -> bool:
        """Are there OTHER active owners of this tenant (excluding the
        current row)? If yes, mutating this row is safe — the tenant
        won't be orphaned."""
        qs = TenantMembership.objects.filter(
            tenant_id=self.tenant_id,
            role="owner",
            is_active=True,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        return qs.exists()

    def clean(self):
        """Refuse a save that would leave the tenant with no active
        owners. Three orphaning paths covered:

          • Existing active owner being deactivated   (is_active False)
          • Existing active owner being demoted       (role change)
          • Direct delete handled in delete() below.
        """
        super().clean()
        was_owner = self._is_contributing_active_owner_now()
        will_be_owner = self._would_be_active_owner_after_save()

        # Only flag transitions FROM contributing TO not-contributing.
        if was_owner and not will_be_owner:
            if not self._tenant_has_other_active_owner():
                from django.core.exceptions import ValidationError
                from .models import Tenant  # avoid circular at import time
                tname = (
                    Tenant.objects.only("business_name")
                    .get(pk=self.tenant_id)
                    .business_name
                )
                # Tell the operator what specifically they changed so
                # they know what to undo or do instead.
                if not self.is_active:
                    why = "deactivate this membership"
                elif self.role != "owner":
                    why = f"change the role from owner to {self.role}"
                else:
                    why = "save this change"
                raise ValidationError(
                    f"Cannot {why}: this is the only active owner of "
                    f"{tname}. Promote another member to owner first, "
                    f"OR add a new owner membership, so the tenant "
                    f"isn't left without an administrator.",
                )

    def save(self, *args, **kwargs):
        """Run clean() on every save path. ModelForm.save() already
        runs full_clean → clean() for us, but direct .save() calls
        from Django shell / management commands / API code skip it.
        Wiring it here guarantees the guard fires regardless of path.
        """
        self.clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Refuse direct deletion of the last active owner.

        Note: when User.delete() is called, the CASCADE on user_id
        bypasses this method (Django invokes the database-level
        cascade, not the Python method). That path is guarded by
        User.delete() instead. This method covers the case where
        someone deletes the membership row directly (admin → Tenant
        memberships → delete a row, or via shell).
        """
        if self.role == "owner" and self.is_active and not self._tenant_has_other_active_owner():
            from django.core.exceptions import ValidationError
            from .models import Tenant
            tname = (
                Tenant.objects.only("business_name")
                .get(pk=self.tenant_id)
                .business_name
            )
            raise ValidationError(
                f"Cannot delete this membership: it is the only "
                f"active owner of {tname}. Promote another member "
                f"to owner first, OR add a new owner membership.",
            )
        return super().delete(*args, **kwargs)


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
    # FBR POS registration for this outlet. The POS ID + Code are issued by
    # FBR when the outlet is registered as a POS under Digital Invoicing.
    # NB: these are NOT sent in the postinvoicedata payload (the Bearer token
    # in fbr_tokens is what binds submissions to the registered POS on FBR's
    # side). We store them for our own traceability, receipts, and to surface
    # the FBR-portal POS ID to operators. See project_pos_fbr_local_fields.
    fbr_pos_id = models.CharField(max_length=50, blank=True, null=True)
    fbr_pos_code = models.CharField(max_length=50, blank=True, null=True)

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
    # Stable per-branch ordinal (1, 2, 3 …) assigned at creation. Drives the
    # per-terminal segment of the invoice number (BRANCH-T{index}-YYYY-NNNN)
    # so two terminals in the same branch can NEVER mint colliding numbers —
    # unlike deriving the index from the (free-text) name. Unique per branch.
    terminal_index = models.PositiveSmallIntegerField(blank=True, null=True)

    # --- Device pairing (Electron terminal onboarding) ---------------------
    # The owner creates the Terminal row in admin-web and gets a short one-time
    # pairing code. On first launch the cashier types the code into the
    # invoiceSolution.exe terminal; the terminal redeems it via the public
    # /api/terminals/pair/ endpoint, which binds THIS device to this Terminal
    # row (stamping device_fingerprint) and returns the branch identity the
    # terminal needs (branch_id, terminal_index, sdc_url). One branch = one POS
    # registration; many terminals can pair to that branch, each a distinct row.
    pairing_code = models.CharField(
        max_length=16, blank=True, null=True, db_index=True,
    )
    pairing_code_expires_at = models.DateTimeField(blank=True, null=True)
    paired_at = models.DateTimeField(blank=True, null=True)
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
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "terminal_index"],
                name="uniq_terminal_branch_index",
                condition=models.Q(terminal_index__isnull=False),
            ),
        ]
        indexes = [
            models.Index(
                fields=["branch"],
                name="idx_terminals_branch",
                condition=models.Q(is_active=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} @ {self.branch_id}"

    def save(self, *args, **kwargs):
        # Auto-assign a stable per-branch terminal_index on first save so every
        # creation path (admin API, implicit default, seed, tests) is covered.
        # Locked + retried so concurrent terminal creations in one branch don't
        # race to the same index (the unique constraint is the final backstop).
        from django.db import transaction

        if self.terminal_index is None and self.branch_id is not None:
            with transaction.atomic():
                taken = (
                    Terminal.objects.select_for_update()
                    .filter(branch_id=self.branch_id, terminal_index__isnull=False)
                    .values_list("terminal_index", flat=True)
                )
                taken_set = set(taken)
                nxt = 1
                while nxt in taken_set:
                    nxt += 1
                self.terminal_index = nxt
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    # --- Pairing helpers ---------------------------------------------------
    PAIRING_CODE_TTL_DAYS = 14

    @staticmethod
    def _generate_pairing_code() -> str:
        """A short, human-typable, unambiguous one-time code (e.g. 'K7P3-9QXM').

        Uses an alphabet with the visually ambiguous chars removed (no 0/O,
        1/I/L) so a cashier reading it off the screen can't mistype it. 8
        chars from a 31-symbol alphabet ≈ 31^8 ≈ 8.5e11 combinations — and
        the code is single-use + expiring, so collisions/guessing aren't a
        concern at our scale.
        """
        import secrets

        alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        return f"{raw[:4]}-{raw[4:]}"

    def issue_pairing_code(self) -> str:
        """(Re)issue a fresh pairing code; persists code + expiry. Returns it."""
        from datetime import timedelta

        from django.utils import timezone

        # Loop on the (rare) unique-ish collision so we never hand out a code
        # that's already live on another terminal.
        for _ in range(5):
            code = self._generate_pairing_code()
            if not Terminal.objects.filter(pairing_code=code).exclude(pk=self.pk).exists():
                break
        self.pairing_code = code
        self.pairing_code_expires_at = timezone.now() + timedelta(
            days=self.PAIRING_CODE_TTL_DAYS,
        )
        self.save(update_fields=["pairing_code", "pairing_code_expires_at", "updated_at"])
        return code

    def clear_pairing_code(self) -> None:
        self.pairing_code = None
        self.pairing_code_expires_at = None
        self.save(update_fields=["pairing_code", "pairing_code_expires_at", "updated_at"])


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
