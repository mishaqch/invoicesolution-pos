"""Tenant + Branch + Terminal + Cashier admin.

The Tenant change form is the single onboarding surface: in one page, a
super-admin captures the business identity, the owner's login, the
subscription, and the module set. On save we create the Tenant + the
owner User + the owner TenantMembership in one transaction so the
operator never has to touch the Users page for tenant onboarding.

Cashier creation lives under this same app (proxy model on User) so all
tenant-scoped people live in the same sidebar group.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
)

from .business_mode import (
    FBR_BUSINESS_NATURE_CHOICES,
    default_modules_for_mode,
)
from .models import Branch, Tenant, TenantMembership, Terminal
from .modules import MODULES, normalise as normalise_modules

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared widgets / helpers
# ---------------------------------------------------------------------------


_PIN_REGEX = r"^\d{6}$"
_PIN_WIDGET_ATTRS = {
    "autocomplete": "new-password",
    "inputmode": "numeric",
    "pattern": "[0-9]{6}",
    "maxlength": "6",
    "minlength": "6",
}
_PIN_ERROR_MESSAGES = {"invalid": "PIN must be exactly 6 digits."}


def _validate_email_globally_unique(email: str, *, exclude_user_id=None) -> None:
    """User.email is unique at the DB level. We surface that as a friendly
    form error before the operator clicks Save, with a hint about WHO is
    already using the address (owner of which tenant, cashier of which
    tenant, or platform admin) so the operator can decide whether they
    meant to attach to that user or pick a different address.

    Phone is also unique app-wide; callers handle that with a sibling
    check via `_validate_phone_globally_unique`.
    """
    if not email:
        return
    qs = User.objects.filter(email__iexact=email)
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    existing = qs.first()
    if existing is None:
        return

    if existing.is_platform_staff:
        where = "an existing platform admin"
    else:
        memberships = list(
            TenantMembership.objects.filter(user=existing, is_active=True)
            .select_related("tenant")
        )
        if memberships:
            where = ", ".join(
                f"{m.get_role_display()} of {m.tenant.business_name}"
                for m in memberships
            )
        else:
            where = "an existing user with no active memberships"
    raise ValidationError(
        f"This email is already used by {where}. Email must be unique "
        f"across the platform — pick a different one, or edit the existing "
        f"user."
    )


class _AccountManagerFieldWrapper(RelatedFieldWidgetWrapper):
    """Same as Django's RelatedFieldWidgetWrapper, but the '+' (add)
    link carries a hint that the new user should be created as an
    Account Manager. The User admin's add_view reads ?platform_role=
    from the GET and pre-selects that role + shows a banner.

    We do NOT subclass to add new fields — we wrap an existing instance
    so all the other URL handling (change/delete/view) stays correct.
    """

    def __init__(self, wrapped: RelatedFieldWidgetWrapper):
        self.__dict__.update(wrapped.__dict__)

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        # The template builds the link as `{{ add_related_url }}?{{ url_params }}`,
        # so we append our flag onto `url_params` (NOT add_related_url, or
        # we'd get a double '?').
        if ctx.get("url_params"):
            ctx["url_params"] = (
                f"{ctx['url_params']}&platform_role=account_manager"
            )
        return ctx


def _validate_phone_globally_unique(phone: str, *, exclude_user_id=None) -> None:
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
# Modules widget (unchanged behaviour, moved here for locality)
# ---------------------------------------------------------------------------


class ModulesCheckboxWidget(forms.CheckboxSelectMultiple):
    template_name = "tenants/admin/modules_checkbox.html"


class ModulesField(forms.MultipleChoiceField):
    def __init__(self, *args, **kwargs):
        choices = [(m["key"], m["label"]) for m in MODULES]
        super().__init__(*args, choices=choices, required=False, **kwargs)

    def clean(self, value):
        return normalise_modules(super().clean(value))


# ---------------------------------------------------------------------------
# Tenant form — unified create + edit
# ---------------------------------------------------------------------------


class TenantAdminForm(forms.ModelForm):
    """Single form that onboards (or edits) a tenant + its owner.

    On CREATE: also creates the owner User + TenantMembership(role=owner).
    On EDIT: the owner identity fields are pulled from the linked owner
    user, edits are pushed back to that row. Password is set only on
    create — on edit, the password field is hidden and a "Reset
    password" link points to Django's password-change view for the
    owner user.
    """

    # --- Business owner ---------------------------------------------------
    # These fields populate the owner User row + create a
    # TenantMembership(role=owner) for them on save. The email +
    # password are the owner's admin-web login credentials — no
    # separate "set up login" step is needed.
    #
    # On EDIT the password block hides itself and shows a "Reset
    # password" link instead, so a routine name/email tweak doesn't
    # accidentally blank the working password.
    #
    # Field labels intentionally omit "Owner —" prefix; the section
    # heading ("Business owner") already establishes ownership context.
    owner_full_name = forms.CharField(
        max_length=255, label="Full name",
        help_text="The owner's name. Shown on receipts and in admin-web.",
        widget=UnfoldAdminTextInputWidget,
    )
    owner_email = forms.EmailField(
        max_length=255, label="Email (used to sign in)",
        help_text=(
            "The owner uses this email to log into admin-web. "
            "Must be unique across the platform."
        ),
        widget=UnfoldAdminEmailInputWidget,
    )
    owner_phone = forms.CharField(
        max_length=20, label="Phone", required=False,
        help_text="Optional. Used for password-reset SMS later.",
        widget=UnfoldAdminTextInputWidget,
    )
    owner_password1 = forms.CharField(
        label="Password (admin-web login)", required=False,
        widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "new-password"}),
        help_text=mark_safe(
            "<span style='font-size:0.75rem;color:#6b7280;'>"
            "At least 8 characters. Not all digits. Not too similar to "
            "the email or name above."
            "</span>"
        ),
    )
    owner_password2 = forms.CharField(
        label="Confirm password", required=False,
        widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "new-password"}),
        help_text=(
            "Re-type the password to confirm there's no typo. "
            "We can't recover it later."
        ),
    )

    # --- FBR taxonomy -----------------------------------------------------
    # `fbr_business_natures` is a Postgres ArrayField(choices=…) on the
    # model. Django's default widget for that is a SimpleArrayField
    # textarea — operator types comma-separated values, which is awful
    # UX for a known 8-item enum. Override with a checkbox grid that
    # stores back into the ArrayField as a list of strings.
    fbr_business_natures = forms.MultipleChoiceField(
        choices=FBR_BUSINESS_NATURE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="FBR business natures",
        help_text=(
            "Tick every nature this business operates as. PRAL accepts "
            "the listed strings verbatim. Required before submitting "
            "invoices to PRAL."
        ),
    )

    # Assigned scenarios — pasted from the tenant's IRIS profile.
    # The choices list is the FULL KNOWN_SCENARIO_META catalog, with
    # the description appended to each code so the operator doesn't
    # need to memorise what SN001 means.
    # Codes for which we don't have a payload-builder yet are tagged
    # "(not yet supported)" in the label — the operator still ticks
    # them so we know what IRIS expects, but the runner will skip
    # them at execution time with status="not_implemented".
    assigned_scenarios = forms.MultipleChoiceField(
        choices=[],  # populated in __init__ from the FBR catalog
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Assigned FBR scenarios (from IRIS) — sandbox onboarding only",
        help_text=(
            "Needed ONLY if this tenant will run sandbox scenario testing "
            "through this platform (it gates production activation and tells "
            "the test runner which scenarios to submit). You can SKIP it for "
            "a tenant FBR already issued a production token to — sandbox was "
            "done on the FBR portal, and production invoices don't use this "
            "list (PRAL classifies each line by saleType; we send no "
            "scenarioId in production). When you do set it, tick exactly what "
            "the tenant's IRIS profile lists (PRAL has no API for it); it "
            "overrides our nature × sector best-guess and selects retail "
            "scenarios (SN026/27/28) for POS sales where assigned."
        ),
    )

    # --- Module config ----------------------------------------------------
    apply_module_defaults = forms.BooleanField(
        label="Reset modules to defaults for this business mode",
        required=False,
        initial=False,
        help_text=(
            "Tick this to replace the module grid below with the default "
            "set for the chosen business mode. POS gets a full counter "
            "setup; Digital Invoicing gets only the back-office surfaces. "
            "Use when switching an existing tenant between modes."
        ),
    )

    modules_enabled = ModulesField(
        widget=ModulesCheckboxWidget,
        help_text=(
            "Sales and FBR are forced on (the platform's core) and stay "
            "enabled regardless of selection. For most tenants leave the "
            "checkbox above ticked at create time and don't hand-edit this "
            "grid."
        ),
    )

    class Meta:
        model = Tenant
        fields = "__all__"

    # --- Init: pre-fill owner fields on edit ------------------------------

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_new = self.instance._state.adding if self.instance else True

        # Populate the assigned_scenarios choices from the FBR catalog.
        # Lazy import — apps.fbr is initialised after apps.tenants in
        # INSTALLED_APPS, so importing at module top-level would race.
        from apps.fbr.scenarios import (
            KNOWN_SCENARIO_META,
            builder_available,
        )
        scenario_choices = []
        for code in sorted(KNOWN_SCENARIO_META.keys()):
            description = KNOWN_SCENARIO_META[code]
            # Label format mirrors the IRIS profile so the operator
            # can visually match what they're ticking against the
            # screen they're copying from.
            suffix = "" if builder_available(code) else " — (not yet supported)"
            scenario_choices.append(
                (code, f"{code} · {description}{suffix}"),
            )
        self.fields["assigned_scenarios"].choices = scenario_choices

        # The Tenant model has its own `phone` + `email` columns separate
        # from the OWNER's. Rename their labels to make the distinction
        # obvious in the rendered form — without these overrides the
        # operator sees two "Phone" / "Email" rows and assumes one is a
        # duplicate of the other.
        for fld, label, help_text in (
            ("phone", "Business phone",
             "Public contact number for this business (shop landline or "
             "main mobile). Printed on invoices. Not the owner's personal "
             "mobile — that goes in 'Owner — phone' above."),
            ("email", "Business email",
             "Public contact email for this business. Not the owner's login "
             "email — that goes in 'Owner — email' above."),
            ("address", "Business address",
             "Street address printed on every invoice."),
        ):
            if fld in self.fields:
                self.fields[fld].label = label
                self.fields[fld].help_text = help_text

        # Friendlier labels for FBR + identity fields.
        _RELABEL = {
            "ntn":  ("NTN",  "National Tax Number. Must be unique across all tenants."),
            "strn": ("STRN", "Sales Tax Registration Number. Optional."),
            "cnic_owner": ("Owner CNIC",
                           "13-digit CNIC of the proprietor. Optional."),
            "fbr_business_natures": (
                "FBR business natures",
                "One or more FBR-defined business natures. Required before "
                "submitting invoices to PRAL.",
            ),
            "fbr_sector": (
                "FBR sector",
                "The single FBR-defined sector this tenant operates in. "
                "Drives the scenarioId list for sandbox testing.",
            ),
            "signup_source": ("Sign-up source",
                              "How did this tenant arrive? e.g. self_serve, sales, reseller."),
            "internal_notes": ("Internal notes (platform-team only)", ""),
            "logo_url": ("Logo URL",
                         "Public URL to the tenant's logo. Shown in admin-web header + receipts."),
        }
        for fld, (label, help_text) in _RELABEL.items():
            if fld in self.fields:
                self.fields[fld].label = label
                if help_text:
                    self.fields[fld].help_text = help_text

        if is_new:
            self.fields["apply_module_defaults"].initial = True
            # Password is required on create only.
            self.fields["owner_password1"].required = True
            self.fields["owner_password2"].required = True
        else:
            self.fields["modules_enabled"].initial = list(
                self.instance.modules_enabled or [],
            )
            # `fbr_business_natures` is a model ArrayField overridden on the
            # form as a MultipleChoiceField. Django's ModelForm doesn't
            # auto-prefill non-model fields — explicitly seed it from the
            # instance so the checkbox grid reflects current saved values.
            self.fields["fbr_business_natures"].initial = list(
                self.instance.fbr_business_natures or [],
            )
            # Same pattern for assigned_scenarios (also a JSONField+grid).
            self.fields["assigned_scenarios"].initial = list(
                self.instance.assigned_scenarios or [],
            )
            owner = self._lookup_owner_user(self.instance)
            self._existing_owner_user = owner
            if owner:
                self.fields["owner_full_name"].initial = owner.full_name
                self.fields["owner_email"].initial = owner.email
                self.fields["owner_phone"].initial = owner.phone or ""
            # On edit we don't touch the password from this form — there's
            # a dedicated "Reset password" link rendered as a readonly
            # field on the admin (see TenantAdmin.owner_password_reset_link).
            self.fields["owner_password1"].widget = forms.HiddenInput()
            self.fields["owner_password2"].widget = forms.HiddenInput()
            self.fields["owner_password1"].required = False
            self.fields["owner_password2"].required = False
            self.fields["owner_password1"].help_text = ""
            self.fields["owner_password2"].help_text = ""

    @staticmethod
    def _lookup_owner_user(tenant: Tenant):
        """Return the User attached to this tenant via an active owner
        membership. If there are multiple owners (rare), the oldest one
        wins; the rest stay as additional owner memberships visible in
        the inline below."""
        m = (
            TenantMembership.objects.filter(
                tenant=tenant, role="owner", is_active=True,
            )
            .select_related("user")
            .order_by("created_at")
            .first()
        )
        return m.user if m else None

    # --- Validation -------------------------------------------------------

    def clean(self):
        cleaned = super().clean()
        is_new = self.instance._state.adding if self.instance else True

        # Email + phone uniqueness across the platform.
        owner_email = (cleaned.get("owner_email") or "").strip()
        owner_phone = (cleaned.get("owner_phone") or "").strip() or None
        existing_owner_id = (
            self._existing_owner_user.pk
            if not is_new and getattr(self, "_existing_owner_user", None)
            else None
        )
        try:
            _validate_email_globally_unique(
                owner_email, exclude_user_id=existing_owner_id,
            )
        except ValidationError as exc:
            self.add_error("owner_email", exc)
        try:
            _validate_phone_globally_unique(
                owner_phone, exclude_user_id=existing_owner_id,
            )
        except ValidationError as exc:
            self.add_error("owner_phone", exc)

        # Password rules — create only.
        if is_new:
            p1 = cleaned.get("owner_password1") or ""
            p2 = cleaned.get("owner_password2") or ""
            if not p1:
                self.add_error("owner_password1", "Set an owner password.")
            elif p1 != p2:
                self.add_error("owner_password2", "Passwords do not match.")
            else:
                from django.contrib.auth.password_validation import validate_password
                try:
                    # Build an in-memory user so password validators that
                    # check "similar to attribute" have something to look at.
                    probe = User(email=owner_email, full_name=cleaned.get("owner_full_name") or "")
                    validate_password(p1, user=probe)
                except ValidationError as exc:
                    for msg in exc.messages:
                        self.add_error("owner_password1", msg)

        return cleaned

    # --- Save: tenant + owner + membership ---
    #
    # The owner User + TenantMembership creation lives in
    # TenantAdmin.save_model + save_related (see below). Django admin
    # never calls `form.save(commit=True)` — it splits the flow as:
    #   1) form.save(commit=False)   → returns unsaved instance
    #   2) admin.save_model()        → instance.save()  (writes tenant)
    #   3) admin.save_related()      → form.save_m2m() + inlines
    # So if we put owner creation inside `form.save(commit=True)`, it
    # never runs from the admin POST path — and we got orphan tenants
    # with no owner. Owner provisioning is now a responsibility of the
    # admin layer, where it can wrap the whole admin flow in one
    # transaction.

    def save(self, commit=True):
        """Standard ModelForm save — touches the Tenant row only.
        Owner User + Membership are created by TenantAdmin.save_model
        + save_related so they participate in the admin's atomic save
        pipeline.
        """
        if self.cleaned_data.get("apply_module_defaults"):
            mode = self.cleaned_data.get("business_mode") or "digital_invoicing"
            self.instance.modules_enabled = normalise_modules(
                default_modules_for_mode(mode),
            )
        return super().save(commit=commit)


# ---------------------------------------------------------------------------
# Inlines on Tenant edit page
# ---------------------------------------------------------------------------


# NOTE: The "Additional memberships" inline used to sit on the Tenant
# edit page so the super-admin could quickly add managers / cashiers /
# accountants. Operators were confused: it looked like a duplicate of
# the Business owner section (same shape: User + Role + active). It
# has been removed in favour of dedicated admin pages — cashiers via
# the Cashier admin (Tenants → Cashiers), and other roles via direct
# `/admin/tenants/tenantmembership/` URLs if absolutely needed. The
# Tenant edit form now stays focused on tenant + owner data only.


# ---------------------------------------------------------------------------
# Tenant admin
# ---------------------------------------------------------------------------


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    # Pull in the shared form polish CSS from the accounts app (consistent
    # input borders, focus rings, fieldset spacing) so the Tenant create +
    # edit pages match the Users page visually instead of inheriting the
    # default browser-ugly form styling.
    class Media:
        css = {"all": (
            "accounts/admin/admin_forms.css",
            "tenants/admin/fbr_connection_toggle.css",
        )}
        # Live-toggle the "FBR sandbox scenarios" fieldset based on the chosen
        # FBR connection type (show only for di_api; hide for ims_sdc) — covers
        # the create page + dropdown changes before save. The server also drops
        # it for saved ims_sdc tenants (get_fieldsets).
        js = ("tenants/admin/fbr_connection_toggle.js",)

    warn_unsaved_form = True
    list_fullwidth = True
    form = TenantAdminForm
    list_display = (
        "business_name", "ntn", "owner_summary",
        "business_mode", "vertical", "subscription_plan", "subscription_status",
        "province", "created_at",
    )
    search_fields = ("business_name", "ntn", "strn",
                     "memberships__user__email")
    list_filter = ("business_type", "business_mode", "vertical", "province",
                   "subscription_plan", "subscription_status", "signup_source")
    readonly_fields = (
        "id", "created_at", "updated_at",
        "onboarding_progress_live", "owner_password_reset_link",
    )
    autocomplete_fields = ("account_manager",)
    # No inlines — the form is focused on tenant + owner data only.
    # Non-owner roles (manager / accountant / etc.) are managed via the
    # TenantMembership admin; cashiers via the Cashier admin.
    inlines = []

    # Same fieldset structure for CREATE and EDIT — the operator should
    # see the same shape of form whether onboarding a new tenant or
    # editing an existing one. The only difference is the owner-login
    # block, which carries password fields on create and a "Reset
    # password" link on edit. Everything diagnostic (onboarding progress,
    # raw onboarding_state JSON, audit timestamps, suspended_at) lives
    # under a single collapsed "Advanced (support triage)" block at the
    # bottom — opened only when the operator needs it.

    @staticmethod
    def _owner_login_fieldset(is_new: bool):
        if is_new:
            return ("Business owner", {
                "fields": (
                    "owner_full_name", "owner_email", "owner_phone",
                    "owner_password1", "owner_password2",
                ),
                "description": (
                    "Enter the business owner's details. The email + "
                    "password below ARE the owner's login — they sign "
                    "in to admin-web with these credentials immediately "
                    "after the tenant is created. Email and phone must "
                    "be unique across the platform."
                ),
            })
        return ("Business owner", {
            "fields": (
                "owner_full_name", "owner_email", "owner_phone",
                "owner_password_reset_link",
            ),
            "description": (
                "The business owner. Their email (above) is their "
                "admin-web login; the password was set when the tenant "
                "was created. Use the 'Reset password' link below to "
                "issue a new password if the owner forgets it."
            ),
        })

    _COMMON_FIELDSETS = (
        ("Business identity", {
            "fields": ("business_name", "ntn", "strn", "cnic_owner",
                       "business_type", "business_mode", "vertical",
                       "fbr_connection_type",
                       "province", "fbr_business_natures", "fbr_sector"),
            "description": (
                "Business mode = the product the tenant signed up for. "
                "POS / IMS = counter terminal + inventory + hardware. "
                "Digital Invoicing = back-office invoice tool only. "
                "Vertical = the KIND of shop (Grocery vs Pharmacy). It only "
                "decides which sections the apps show the tenant — a Pharmacy "
                "sees batch/expiry/supplier tools, a Grocery doesn't. It does "
                "NOT change what's enabled (that's Modules below). "
                "FBR connection type = HOW they reach FBR: 'Direct DI-API' "
                "(PRAL Bearer token + sandbox scenarios) vs 'IMS / SDC' (the "
                "FBR Fiscalization service on the shop PC — POS ID only, no "
                "token, no scenarios). This hides the irrelevant FBR controls "
                "for each tenant."
            ),
        }),
        ("FBR sandbox scenarios", {
            "fields": ("assigned_scenarios", "fbr_test_buyer_ntn"),
            "description": (
                "FBR assigns each Digital Invoicing tenant a specific "
                "list of scenarios in IRIS. Paste that list here so the "
                "sandbox runner only tests scenarios this tenant is "
                "actually expected to demonstrate. Leave empty to use "
                "the platform's nature × sector best-guess default. "
                "If ANY of the assigned scenarios needs a registered "
                "buyer (SN001, SN005), also set the test buyer NTN — "
                "PRAL's documented test NTN is not actually registered."
            ),
        }),
        ("Business contact", {
            "fields": ("address", "phone", "email", "logo_url"),
            "description": (
                "Public contact for the business — printed on invoices, "
                "shown in admin-web. Distinct from the OWNER's email + "
                "phone above."
            ),
        }),
        ("Subscription", {
            "fields": ("subscription_plan", "subscription_status",
                       "trial_ends_at", "next_billing_at"),
        }),
        ("Account manager + sign-up", {
            "fields": ("signup_source", "account_manager", "internal_notes", "tags"),
        }),
        ("Modules enabled", {
            "fields": ("apply_module_defaults", "modules_enabled"),
            "description": (
                "Per-tenant feature catalog. For new tenants, just tick "
                "'Reset modules to defaults' and Save — the right set "
                "for the chosen business mode is applied automatically."
            ),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        is_new = obj is None
        common = self._COMMON_FIELDSETS
        # Scenarios + test-buyer NTN are DI-API / sandbox-only. An existing
        # tenant on the FBR IMS / SDC Fiscalization service has no token and
        # runs no sandbox scenarios, so hide that fieldset for them to keep the
        # form clean + relevant. (Kept on CREATE, where the connection type
        # isn't chosen yet; it drops off once the tenant is saved as ims_sdc.)
        if obj is not None and getattr(obj, "fbr_connection_type", None) == "ims_sdc":
            common = tuple(
                fs for fs in common if fs[0] != "FBR sandbox scenarios"
            )
        fieldsets = [self._owner_login_fieldset(is_new), *common]
        if not is_new:
            # Advanced block — read-only diagnostic info collapsed by
            # default. Operator opens it only for support triage or to
            # tweak the raw onboarding_state JSON.
            fieldsets.append(
                ("Advanced (support triage)", {
                    "classes": ("collapse",),
                    "fields": (
                        "suspended_at",
                        "onboarding_progress_live",
                        "onboarding_state",
                        "id", "created_at", "updated_at",
                    ),
                    "description": (
                        "Diagnostic info. Onboarding progress is computed "
                        "live from real data. The JSON below stores wizard "
                        "state (dismissed_at, manual overrides) and is "
                        "auto-mirrored from the live flags."
                    ),
                }),
            )
        return tuple(fieldsets)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """When the operator clicks the '+' next to Account Manager,
        we want to take them to the Users admin add page WITH a hint
        that the new user should be tagged as `platform_role=account_manager`.

        We hook `formfield_for_dbfield` (not formfield_for_foreignkey)
        because Django wraps the FK widget in RelatedFieldWidgetWrapper
        AFTER formfield_for_foreignkey returns — so by intercepting at
        the outer hook we see the already-wrapped widget and can
        substitute our subclass cleanly.
        """
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if (
            formfield is not None
            and db_field.name == "account_manager"
            and isinstance(formfield.widget, RelatedFieldWidgetWrapper)
        ):
            formfield.widget = _AccountManagerFieldWrapper(formfield.widget)
        return formfield

    # --- Display helpers --------------------------------------------------

    @admin.display(description="Owner")
    def owner_summary(self, obj):
        owner = TenantAdminForm._lookup_owner_user(obj)
        if not owner:
            return format_html(
                '<span style="color:#dc2626;font-size:11px;">'
                '⚠ no active owner</span>'
            )
        return format_html(
            '<span style="font-size:12px;">{}<br>'
            '<em style="opacity:0.7;font-size:11px;">{}</em></span>',
            owner.full_name or "—", owner.email,
        )

    @admin.display(description="Password")
    def owner_password_reset_link(self, obj):
        owner = TenantAdminForm._lookup_owner_user(obj) if obj else None
        if not owner:
            return mark_safe(
                '<span style="opacity:.6;">No owner user yet.</span>'
            )
        url = reverse("admin:auth_user_password_change", args=[owner.pk])
        return format_html(
            '<a href="{}" class="inline-flex items-center gap-1 '
            'text-primary-600 hover:underline dark:text-primary-500" '
            'style="font-size:0.85rem;">'
            '<span class="material-symbols-outlined" '
            'style="font-size:1rem;">key</span> Reset owner password</a>',
            url,
        )

    @admin.display(description="Onboarding progress (live)")
    def onboarding_progress_live(self, obj):
        from apps.catalog.models import Product
        from apps.sales.models import Invoice

        branches_count = Branch.objects.filter(
            tenant=obj, deleted_at__isnull=True,
        ).count()
        terminals_count = Terminal.objects.filter(tenant=obj).count()
        active_terminals = Terminal.objects.filter(
            tenant=obj, is_active=True,
        ).count()
        products_count = Product.objects.filter(
            tenant=obj, deleted_at__isnull=True,
        ).count()
        invoices_count = Invoice.objects.for_tenant(obj.id).count()

        def row(label, ok, detail=""):
            icon = "✅" if ok else "⏳"
            color = "#15803d" if ok else "#a16207"
            return format_html(
                '<div style="margin:2px 0;color:{};">{} <strong>{}</strong>'
                '<span style="opacity:.7;margin-left:8px;">{}</span></div>',
                color, icon, label, detail,
            )

        rows = [
            row("Branch added", branches_count > 0, f"{branches_count} branch(es)"),
            row("Terminal registered",
                terminals_count > 0,
                f"{terminals_count} total / {active_terminals} active"),
            row("Product added", products_count > 0, f"{products_count} SKU(s)"),
            row("First sale recorded",
                invoices_count > 0,
                f"{invoices_count} invoice(s)"),
        ]
        body = mark_safe("".join(str(r) for r in rows))
        return format_html(
            '<div style="font-family:system-ui,sans-serif;font-size:13px;'
            'line-height:1.5;">{}</div>',
            body,
        )

    # --- Two-tier admin hierarchy ----------------------------------------

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None:
            return True
        if request.user.is_superuser:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    # --- Owner provisioning at admin save time ---------------------------
    #
    # Django admin splits the form-save into save_model (writes the
    # instance) and save_related (m2m + inlines). For atomicity we wrap
    # both in a single transaction.atomic() block via _changeform_view's
    # built-in `transact_atomic_requests` mechanism — but the simplest
    # and most-reliable approach is to explicitly run our owner-write
    # inside save_related (which fires AFTER save_model) and rely on
    # `ATOMIC_REQUESTS=True` on the postgres backend OR wrap the body
    # of save_model itself in an atomic block.
    #
    # We choose the explicit atomic block. If anything in here raises,
    # both the Tenant row AND any partial owner row are rolled back —
    # no more orphan tenants.

    def save_model(self, request, obj, form, change):
        """Persist the Tenant. Owner User + Membership are created here
        too (for `add`) or updated (for `change`) inside one transaction
        with the tenant write.
        """
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if not change:
                # CREATE flow: spin up the owner User + membership.
                cleaned = form.cleaned_data
                owner = User.objects.create(
                    email=cleaned["owner_email"],
                    full_name=cleaned["owner_full_name"],
                    phone=cleaned.get("owner_phone") or None,
                    is_active=True,
                    is_staff=False,
                    is_platform_staff=False,
                )
                owner.set_password(cleaned["owner_password1"])
                owner.save()
                TenantMembership.objects.create(
                    tenant=obj,
                    user=owner,
                    role="owner",
                    is_active=True,
                )
            else:
                # EDIT flow: push name/email/phone changes onto the
                # existing owner User row (if there is one — there
                # should be, but defensive guard).
                existing_owner = getattr(form, "_existing_owner_user", None)
                if existing_owner:
                    cleaned = form.cleaned_data
                    existing_owner.full_name = cleaned["owner_full_name"]
                    existing_owner.email = cleaned["owner_email"]
                    existing_owner.phone = (
                        cleaned.get("owner_phone") or None
                    )
                    existing_owner.save(
                        update_fields=[
                            "full_name", "email", "phone", "updated_at",
                        ],
                    )

    # --- After create: go to the tenant list page.
    #
    # Previously we redirected to the new tenant's edit page so the
    # operator could "review" the populated record. That confused the
    # operator: the edit page is structurally different (extra
    # 'Additional memberships' inline, 'Advanced (support triage)'
    # collapsed block) so it looks like the create form re-rendered
    # incomplete or with new sections. Instead, follow Django admin's
    # default: list page + success flash, so the operator clearly sees
    # "tenant X was added" and the row in the list.
    #
    # `_addanother` and `_continue` are only honoured server-side as a
    # safety net — the buttons themselves are suppressed on the create
    # page (see render_change_form below) so a normal operator never
    # triggers them.
    def response_add(self, request, obj, post_url_continue=None):
        if "_addanother" in request.POST:
            return HttpResponseRedirect(
                reverse("admin:tenants_tenant_add",
                        current_app=self.admin_site.name)
            )
        if "_continue" in request.POST:
            return HttpResponseRedirect(
                reverse("admin:tenants_tenant_change", args=[obj.pk],
                        current_app=self.admin_site.name),
            )
        return HttpResponseRedirect(
            reverse("admin:tenants_tenant_changelist",
                    current_app=self.admin_site.name),
        )

    def render_change_form(self, request, context, add=False, change=False,
                           form_url="", obj=None):
        """One primary action everywhere: 'Save'.

        Suppress 'Save and add another' + 'Save and continue editing'
        on BOTH the create and edit pages. The product principle (per
        operator request): the tenant is created and edited from a
        single, complete form — don't ask the operator to choose
        between "save and go back to working on this" vs "save and
        move on", just save and return to the list.
        """
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(
            request, context, add=add, change=change,
            form_url=form_url, obj=obj,
        )


# ---------------------------------------------------------------------------
# Tenant memberships admin — kept for raw-edit access, mostly invisible
# ---------------------------------------------------------------------------


@admin.register(TenantMembership)
class TenantMembershipAdmin(ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active", "created_at")
    search_fields = ("tenant__business_name", "user__email", "user__full_name")
    list_filter = ("role", "is_active")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant", "user")

    def has_module_permission(self, request):
        # Hide from the sidebar's "show all applications" list — managed
        # via Tenant + Cashier admins instead. Direct URL still works.
        return False

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
            messages.error(request, msg)
            return HttpResponseRedirect(
                reverse(
                    f"admin:{self.opts.app_label}_{self.opts.model_name}_change",
                    args=[object_id],
                ),
            )

    def delete_queryset(self, request, queryset):
        blocked, deleted = [], 0
        for obj in queryset:
            try:
                obj.delete()
                deleted += 1
            except ValidationError as e:
                msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
                blocked.append(
                    f"{obj.tenant.business_name} ({obj.role} membership): {msg}",
                )
        if deleted:
            messages.success(
                request,
                f"Deleted {deleted} membership{'s' if deleted != 1 else ''}.",
            )
        for line in blocked:
            messages.error(request, line)


# ---------------------------------------------------------------------------
# Branch / Terminal admin
# ---------------------------------------------------------------------------


@admin.register(Branch)
class BranchAdmin(ModelAdmin):
    class Media:
        css = {"all": ("accounts/admin/admin_forms.css",)}

    list_display = ("name", "code", "tenant", "city", "province",
                    "is_active", "is_default")
    search_fields = ("name", "code", "tenant__business_name", "city")
    list_filter = ("tenant", "province", "is_active", "is_default")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("tenant",)


@admin.register(Terminal)
class TerminalAdmin(ModelAdmin):
    class Media:
        css = {"all": ("accounts/admin/admin_forms.css",)}

    list_display = ("name", "branch", "tenant", "is_active", "last_seen_at")
    search_fields = ("name", "device_fingerprint", "branch__name",
                     "tenant__business_name")
    list_filter = ("tenant", "branch", "is_active", "customer_display_enabled")
    readonly_fields = ("id", "created_at", "updated_at",
                       "last_seen_at", "last_synced_at")
    autocomplete_fields = ("tenant", "branch")


# ---------------------------------------------------------------------------
# Cashier admin — User proxy scoped to TenantMembership(role=cashier)
# ---------------------------------------------------------------------------


class Cashier(User):
    """Proxy model: a User whose only relationship to the platform is a
    cashier membership at exactly one tenant.

    Lives under the Tenants app in the sidebar so all tenant-scoped
    people sit in one place. The "Add cashier" page captures email,
    PIN, and the tenant in one shot.
    """

    class Meta:
        proxy = True
        verbose_name = "Cashier"
        verbose_name_plural = "Cashiers"
        app_label = "tenants"


class CashierCreationForm(forms.ModelForm):
    """Create form for a cashier: User + TenantMembership(role=cashier) in
    one transaction. No admin-web password (PIN-only login)."""

    # Same Unfold-widget treatment as the Tenant form: explicit form
    # fields don't get Unfold's class string by default, so wire them
    # to the matching Unfold widget for consistent styling.
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.order_by("business_name"),
        required=True, label="Tenant",
        help_text="Which tenant's terminal this cashier rings up sales on.",
        widget=UnfoldAdminSelectWidget,
    )
    set_pin = forms.RegexField(
        regex=_PIN_REGEX,
        required=True,
        label="Terminal PIN (6 digits)",
        widget=UnfoldAdminPasswordWidget(attrs=_PIN_WIDGET_ATTRS),
        error_messages=_PIN_ERROR_MESSAGES,
        help_text=(
            "Exactly 6 digits. Cashier types this on the POS terminal. "
            "Hashed before storage — write it down before saving."
        ),
    )

    class Meta:
        model = Cashier
        fields = ("full_name", "email", "phone", "is_active")

    def clean_email(self):
        email = self.cleaned_data.get("email")
        _validate_email_globally_unique(email)
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip() or None
        _validate_phone_globally_unique(phone)
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_platform_staff = False
        user.is_staff = False
        user.set_unusable_password()
        user.set_pin(self.cleaned_data["set_pin"])
        if commit:
            with transaction.atomic():
                user.save()
                TenantMembership.objects.create(
                    user=user,
                    tenant=self.cleaned_data["tenant"],
                    role="cashier",
                    is_active=True,
                )
        return user


class CashierChangeForm(forms.ModelForm):
    """Edit form for an existing cashier. Tenant is read-only here —
    re-assigning a cashier to a different tenant is rare; do it via
    Tenant memberships if really needed."""

    set_pin = forms.RegexField(
        regex=_PIN_REGEX,
        required=False,
        label="Set new PIN",
        widget=UnfoldAdminPasswordWidget(attrs=_PIN_WIDGET_ATTRS),
        error_messages=_PIN_ERROR_MESSAGES,
        help_text="Leave blank to keep the existing PIN. Exactly 6 digits to rotate.",
    )
    clear_pin = forms.BooleanField(
        required=False, label="Clear PIN",
        help_text=(
            "Tick + save to remove this cashier's PIN. They won't be able "
            "to log in to the terminal until a new one is set."
        ),
    )

    class Meta:
        model = Cashier
        fields = ("full_name", "email", "phone", "is_active")

    def clean_email(self):
        email = self.cleaned_data.get("email")
        _validate_email_globally_unique(
            email, exclude_user_id=self.instance.pk if self.instance else None,
        )
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip() or None
        _validate_phone_globally_unique(
            phone, exclude_user_id=self.instance.pk if self.instance else None,
        )
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("set_pin") and cleaned.get("clear_pin"):
            raise ValidationError(
                "Pick one: set a new PIN or clear it. Not both.",
            )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("set_pin"):
            user.set_pin(self.cleaned_data["set_pin"])
        if self.cleaned_data.get("clear_pin"):
            user.pin_hash = None
        if commit:
            user.save()
        return user


@admin.register(Cashier)
class CashierAdmin(ModelAdmin):
    """Admin for cashier users. Filters the User queryset to people with
    an active cashier membership only — owners / managers / platform
    admins never appear here."""

    class Media:
        css = {"all": ("accounts/admin/admin_forms.css",)}

    add_form = CashierCreationForm
    form = CashierChangeForm
    list_fullwidth = True
    list_display = (
        "email", "full_name", "tenant_summary", "pin_status",
        "is_active", "last_login",
    )
    list_filter = ("is_active", "memberships__tenant")
    search_fields = ("email", "full_name", "phone",
                     "memberships__tenant__business_name")
    ordering = ("email",)
    readonly_fields = ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until", "pin_status")

    _CREATE_FIELDSETS = (
        ("Tenant", {"fields": ("tenant",)}),
        ("Identity", {"fields": ("full_name", "email", "phone")}),
        ("Terminal PIN", {"fields": ("set_pin",)}),
        ("State", {"fields": ("is_active",)}),
    )
    _EDIT_FIELDSETS = (
        ("Identity", {"fields": ("full_name", "email", "phone")}),
        ("Terminal PIN", {
            "fields": ("pin_status", "set_pin", "clear_pin"),
            "description": (
                "The hashed PIN is never shown — rotate it or clear it here."
            ),
        }),
        ("State", {"fields": ("is_active",)}),
        ("Activity", {
            "classes": ("collapse",),
            "fields": ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until"),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self._CREATE_FIELDSETS
        return self._EDIT_FIELDSETS

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        else:
            kwargs["form"] = self.form
        return super().get_form(request, obj, change=change, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.filter(
                memberships__role="cashier",
                memberships__is_active=True,
            )
            .distinct()
            .prefetch_related("memberships__tenant")
        )

    # Display helpers

    @admin.display(description="Tenant")
    def tenant_summary(self, obj):
        memberships = [
            m for m in obj.memberships.all()
            if m.role == "cashier" and m.is_active
        ]
        if not memberships:
            return "—"
        return format_html(
            "<br>".join(
                f"<span style='font-size:12px;'>{m.tenant.business_name}</span>"
                for m in memberships
            )
        )

    @admin.display(description="PIN")
    def pin_status(self, obj):
        if obj and obj.pin_hash:
            return format_html(
                '<span style="background:#dcfce7;color:#15803d;'
                'padding:2px 8px;border-radius:9999px;font-size:11px;'
                'font-weight:600;">✓ Set</span>'
            )
        return format_html(
            '<span style="background:#fef3c7;color:#92400e;'
            'padding:2px 8px;border-radius:9999px;font-size:11px;'
            'font-weight:600;">⚠ Not set</span>'
        )

    # Two-tier hierarchy: only superuser can delete cashiers.
    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    # Same UX principle as TenantAdmin — one form, one Save button,
    # return to the list. Cashiers are created and edited from a single
    # complete form; we don't ask "save and continue editing".
    def render_change_form(self, request, context, add=False, change=False,
                           form_url="", obj=None):
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(
            request, context, add=add, change=change,
            form_url=form_url, obj=obj,
        )

    def response_add(self, request, obj, post_url_continue=None):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        return HttpResponseRedirect(
            reverse("admin:tenants_cashier_changelist",
                    current_app=self.admin_site.name),
        )
