"""User model.

Custom AUTH_USER_MODEL keyed on email (no `username` field). Mirrors
DATABASE_SCHEMA.md §1 `users`. Deviations from raw SQL noted inline.
"""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from core.uuid7 import uuid7

from .managers import UserManager

LANGUAGES = (
    ("en", "English"),
    ("ur", "Urdu"),
)


class User(AbstractBaseUser, PermissionsMixin):
    """A person. Can belong to multiple tenants via TenantMembership.

    Field mapping notes (vs DATABASE_SCHEMA.md §1):
      - id: UUIDField with our uuid7 helper (Postgres column default added in
            a RunSQL migration, so direct SQL inserts also work).
      - email: 255 chars (Django's default EmailField is 254; widened).
      - password (Django attr) → DB column `password_hash` via db_column.
      - last_login (Django attr) → DB column `last_login_at` via db_column.
      - password_changed_at: tracked via override on set_password().
      - is_staff: per the schema, this means "Anthropic-side support staff",
            which lines up with Django's notion of admin access.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    email = models.EmailField(max_length=255, unique=True)
    phone = models.CharField(max_length=20, unique=True, blank=True, null=True)
    full_name = models.CharField(max_length=255)

    # Django reads this as `password`; DB column is named to match the schema.
    password = models.CharField(max_length=255, db_column="password_hash")

    pin_hash = models.CharField(max_length=255, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Phase 0 platform stub. Distinct from is_staff (Django admin access):
    # is_platform_staff means "works for the SaaS operator, not a tenant".
    # Platform staff can log into platform-web (when Phase 9 lands) and
    # access /api/platform/*; they are explicitly BLOCKED from /api/v1/*
    # tenant endpoints unless mid-impersonation (Phase 9 feature).
    is_platform_staff = models.BooleanField(
        default=False,
        help_text="Works for the SaaS operator (us), not a tenant.",
    )
    platform_role = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=(
            ("super_admin", "Super admin"),
            ("billing_admin", "Billing admin"),
            ("support_lead", "Support lead"),
            ("support_agent", "Support agent"),
            ("sales_lead", "Sales lead"),
            ("sales_rep", "Sales rep"),
            ("read_only_observer", "Read-only observer"),
        ),
        help_text="Empty for tenant users; set when is_platform_staff=true.",
    )

    last_login = models.DateTimeField(blank=True, null=True, db_column="last_login_at")
    password_changed_at = models.DateTimeField(auto_now_add=True)
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)

    preferred_language = models.CharField(
        max_length=10, choices=LANGUAGES, default="en"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.email

    # --- Password / PIN helpers -------------------------------------------

    def set_password(self, raw_password):  # type: ignore[override]
        super().set_password(raw_password)
        from django.utils import timezone
        self.password_changed_at = timezone.now()

    def set_pin(self, raw_pin: str) -> None:
        if not raw_pin or not raw_pin.isdigit() or not 4 <= len(raw_pin) <= 6:
            raise ValueError("PIN must be 4–6 digits.")
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin: str) -> bool:
        if not self.pin_hash:
            return False
        return check_password(raw_pin, self.pin_hash)

    # --- Safe-delete guard ------------------------------------------------

    def tenants_where_last_active_owner(self):
        """Return tenants where THIS user is the only active owner.

        Deleting the user would leave those tenants with zero owners —
        no one able to manage them via the React admin. The admin's
        delete flow + the model's delete() both consult this list to
        block the deletion with a clear error.

        Returns: queryset of Tenant rows (empty if safe to delete).
        """
        from apps.tenants.models import Tenant, TenantMembership

        # Tenants where THIS user has an active owner membership.
        owned_tenant_ids = list(
            TenantMembership.objects.filter(
                user=self, role="owner", is_active=True,
            ).values_list("tenant_id", flat=True)
        )
        if not owned_tenant_ids:
            return Tenant.objects.none()

        # Of those, which still have OTHER active owners?
        other_owners_q = (
            TenantMembership.objects.filter(
                tenant_id__in=owned_tenant_ids,
                role="owner",
                is_active=True,
            )
            .exclude(user=self)
            .values_list("tenant_id", flat=True)
            .distinct()
        )
        tenants_with_other_owners = set(other_owners_q)
        last_owner_tenant_ids = [
            t_id for t_id in owned_tenant_ids
            if t_id not in tenants_with_other_owners
        ]
        return Tenant.objects.filter(pk__in=last_owner_tenant_ids)

    def delete(self, *args, **kwargs):
        """Refuse to delete a user who is the LAST active owner of any
        tenant. Forces the operator to either (a) promote another
        member to owner OR (b) explicitly remove the membership first.

        This guard fires at the model layer so it catches all paths:
        Django admin form, bulk-delete admin action, Django shell,
        management commands. Defense in depth — even if someone
        bypasses the admin overrides, the model itself refuses.
        """
        last_owner_of = list(self.tenants_where_last_active_owner())
        if last_owner_of:
            from django.core.exceptions import ValidationError
            names = ", ".join(t.business_name for t in last_owner_of)
            raise ValidationError(
                f"Cannot delete {self.email}: this user is the only "
                f"active owner of {names}. Promote another member to "
                f"owner first, OR remove these owner memberships, "
                f"so the tenant isn't left without an administrator.",
            )
        return super().delete(*args, **kwargs)
