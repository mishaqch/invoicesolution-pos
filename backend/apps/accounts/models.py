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
