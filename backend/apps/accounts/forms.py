"""Admin forms for the User model — platform admins only.

Tenant-side users (owner, manager, cashier) are created via the Tenant
and Cashier admins under `apps.tenants.admin`. The Users page in the
Django admin lists ONLY platform-staff rows; its add form creates
platform admins.

The bundle picker is the curated permission UI documented in
`apps.accounts.platform_perms`. It stores transient state on the form;
on save we translate ticked bundles into auth.Permission rows.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth.models import Permission
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from unfold.forms import (
    UserChangeForm as UnfoldUserChangeForm,
    UserCreationForm as UnfoldUserCreationForm,
)
from unfold.widgets import UnfoldAdminSelectWidget

from .platform_perms import (
    PLATFORM_PERMISSION_BUNDLES,
    all_bundle_perm_keys,
    bundle_for_permission,
    bundle_perm_keys,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Global email + phone uniqueness — surfaced as friendly form errors
# instead of a downstream IntegrityError. User.email and User.phone are
# both unique=True at the DB level; this just makes the rejection
# friendlier and tells the operator who is already using the address.
# ---------------------------------------------------------------------------


def _explain_email_in_use(existing) -> str:
    """Human-readable description of which role/tenant a clashing email
    already belongs to. Used to tell the operator "this address is the
    owner of Tenant X" instead of just "already taken"."""
    if existing.is_platform_staff:
        return "an existing platform admin"
    from apps.tenants.models import TenantMembership
    memberships = list(
        TenantMembership.objects.filter(user=existing, is_active=True)
        .select_related("tenant")
    )
    if memberships:
        return ", ".join(
            f"{m.get_role_display()} of {m.tenant.business_name}"
            for m in memberships
        )
    return "an existing user with no active memberships"


def validate_email_globally_unique(email: str, *, exclude_user_id=None) -> None:
    """Raise ValidationError if `email` is already used by another User.
    Surfaces WHO already uses it so the operator can decide whether
    they meant to edit that user or pick a different address.
    """
    if not email:
        return
    qs = User.objects.filter(email__iexact=email)
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    existing = qs.first()
    if existing is None:
        return
    raise ValidationError(
        f"This email is already used by {_explain_email_in_use(existing)}. "
        f"Email must be unique across the platform — pick a different "
        f"address, or edit the existing user."
    )


def validate_phone_globally_unique(phone: str, *, exclude_user_id=None) -> None:
    """Phone is unique on the User table; same idea as email."""
    if not phone:
        return
    qs = User.objects.filter(phone=phone)
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    if qs.exists():
        raise ValidationError(
            "This phone number is already linked to another account. "
            "Pick a different number."
        )


# ---------------------------------------------------------------------------
# Permission bundle widget + delegation rule
# ---------------------------------------------------------------------------


def _bundles_editor_can_grant(editor) -> set[str]:
    """Which bundles is `editor` allowed to grant to other users?

    - Superuser: all bundles.
    - Non-superuser platform staff: only bundles whose underlying
      permissions they hold themselves (no privilege escalation).
    - None / anonymous: empty set.
    """
    if editor is None:
        return set()
    if editor.is_superuser:
        return {b["key"] for b in PLATFORM_PERMISSION_BUNDLES}
    held: set[str] = set()
    editor_perm_pairs = {
        (p.content_type.app_label, p.codename)
        for p in editor.user_permissions.select_related("content_type").all()
    }
    for b in PLATFORM_PERMISSION_BUNDLES:
        needed = bundle_perm_keys(b["key"])
        if needed.issubset(editor_perm_pairs):
            held.add(b["key"])
    return held


class PermissionBundleWidget(forms.CheckboxSelectMultiple):
    """Renders the bundle list with description + label per checkbox."""

    template_name = "accounts/admin/permission_bundles.html"

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        if value is None:
            selected_set: set[str] = set()
        else:
            selected_set = {str(v) for v in value}
        catalog = self.attrs.get("bundles") or []
        ctx["widget"]["bundles"] = [
            {
                "key": b["key"],
                "label": b["label"],
                "description": b["description"],
                "checked": b["key"] in selected_set,
            }
            for b in catalog
        ]
        return ctx


def _populate_bundles_field(field, request_user):
    """Filter the bundle choices + widget catalog to what `request_user`
    is allowed to grant. Mutates the field in place."""
    field.widget = PermissionBundleWidget()
    allowed = _bundles_editor_can_grant(request_user)
    catalog = [b for b in PLATFORM_PERMISSION_BUNDLES if b["key"] in allowed]
    field.choices = [(b["key"], b["label"]) for b in catalog]
    field.widget.attrs["bundles"] = catalog


def _apply_ticked_bundles_to_user(user, ticked_bundles):
    """Translate a list of bundle keys into auth.Permission rows on the
    user. Preserves any non-bundle perms granted via the advanced widget."""
    target_pairs: set[tuple[str, str]] = set()
    for b in ticked_bundles:
        target_pairs |= bundle_perm_keys(b)
    if target_pairs:
        target_q = Permission.objects.none()
        for app_label in {p[0] for p in target_pairs}:
            codenames = {p[1] for p in target_pairs if p[0] == app_label}
            target_q = target_q | Permission.objects.filter(
                content_type__app_label=app_label,
                codename__in=codenames,
            )
        new_bundle_perms = list(target_q.distinct())
    else:
        new_bundle_perms = []

    all_bundle_pairs = all_bundle_perm_keys()
    current_perms = user.user_permissions.select_related("content_type").all()
    outside_bundle_perms = [
        p for p in current_perms
        if (p.content_type.app_label, p.codename) not in all_bundle_pairs
    ]
    final_perm_pks = list({p.pk for p in new_bundle_perms + outside_bundle_perms})
    user.user_permissions.set(final_perm_pks)


# ---------------------------------------------------------------------------
# Create form — platform admins only
# ---------------------------------------------------------------------------


_PLATFORM_ROLE_CHOICES = (
    ("", "— Pick a platform role —"),
    ("super_admin", "Super admin"),
    ("account_manager", "Account manager"),
    ("billing_admin", "Billing admin"),
    ("support_lead", "Support lead"),
    ("support_agent", "Support agent"),
    ("sales_lead", "Sales lead"),
    ("sales_rep", "Sales rep"),
    ("read_only_observer", "Read-only observer"),
)


_PASSWORD_RULES_HTML = mark_safe(
    "<span style='font-size:0.75rem;color:#6b7280;'>"
    "At least 8 characters. Not all digits. Not too similar to "
    "the email or name above."
    "</span>"
)


class PlatformUserCreationForm(UnfoldUserCreationForm):
    """Create a platform-staff (super-admin operator) user.

    Captures identity + password + role + permission bundles on one page.
    On save, the user is flagged `is_platform_staff=True` and `is_staff=True`
    (Django admin access). Tenant memberships are explicitly NOT created
    here — tenant-side users go through the Tenant / Cashier admins.
    """

    platform_role = forms.ChoiceField(
        choices=_PLATFORM_ROLE_CHOICES,
        required=True,
        label="Platform role",
        help_text=(
            "Determines which control-plane areas this person belongs to. "
            "Refine the granted permissions via the bundles below."
        ),
        # Use Unfold's select widget so the dropdown gets the same
        # border / focus ring / dark-mode treatment as the rest of the
        # form. Without this, ChoiceField defaults to a bare browser
        # <select> with no Unfold class string.
        widget=UnfoldAdminSelectWidget,
    )
    permission_bundles = forms.MultipleChoiceField(
        required=False,
        choices=[],  # populated in __init__
        label="Platform permissions",
        help_text=(
            "Tick the bundles this operator needs. Each bundle grants "
            "view/add/change/delete on a coherent set of related models."
        ),
    )

    class Meta(UnfoldUserCreationForm.Meta):
        from apps.accounts.models import User as _UserModel
        model = _UserModel
        fields = ("email", "full_name", "phone")

    def __init__(self, *args, **kwargs):
        self._request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        _populate_bundles_field(self.fields["permission_bundles"], self._request_user)
        if "password1" in self.fields:
            self.fields["password1"].help_text = _PASSWORD_RULES_HTML
        if "password2" in self.fields:
            self.fields["password2"].help_text = (
                "Re-type the password to confirm there's no typo."
            )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        validate_email_globally_unique(email)
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip() or None
        validate_phone_globally_unique(phone)
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_platform_staff = True
        user.is_staff = True
        user.platform_role = self.cleaned_data["platform_role"]
        if commit:
            user.save()
            self._save_m2m()
        return user

    def _save_m2m(self):
        super()._save_m2m()
        if not self.instance.pk:
            return
        ticked = list(self.cleaned_data.get("permission_bundles") or [])
        _apply_ticked_bundles_to_user(self.instance, ticked)


# ---------------------------------------------------------------------------
# Change form — platform admins only
# ---------------------------------------------------------------------------


class PlatformUserChangeForm(UnfoldUserChangeForm):
    """Edit form for platform-staff users.

    Adds the curated `permission_bundles` field; pre-ticks bundles
    derived from the user's current permissions. A non-superuser
    editor can only grant bundles they themselves hold (delegation
    safety).
    """

    permission_bundles = forms.MultipleChoiceField(
        required=False,
        widget=PermissionBundleWidget,
        choices=[],  # populated in __init__
        label="Platform permissions",
        help_text=(
            "Tick the bundles this operator needs. Each bundle grants "
            "view/add/change/delete on a set of related models."
        ),
    )

    class Meta(UnfoldUserChangeForm.Meta):
        exclude = ("username", "date_joined", "last_login")

    def __init__(self, *args, **kwargs):
        self._request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        _populate_bundles_field(self.fields["permission_bundles"], self._request_user)

        if self.instance and self.instance.pk:
            current_bundles: set[str] = set()
            for p in self.instance.user_permissions.select_related("content_type").all():
                bkey = bundle_for_permission(p.content_type.app_label, p.codename)
                if bkey:
                    current_bundles.add(bkey)
            self.fields["permission_bundles"].initial = list(current_bundles)

    def clean_email(self):
        email = self.cleaned_data.get("email")
        validate_email_globally_unique(
            email, exclude_user_id=self.instance.pk if self.instance else None,
        )
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip() or None
        validate_phone_globally_unique(
            phone, exclude_user_id=self.instance.pk if self.instance else None,
        )
        return phone

    def _save_m2m(self):
        super()._save_m2m()
        if not self.instance.pk:
            return
        ticked = list(self.cleaned_data.get("permission_bundles") or [])
        _apply_ticked_bundles_to_user(self.instance, ticked)
