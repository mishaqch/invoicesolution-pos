"""User admin — opinionated about the platform-staff vs tenant-user split.

The Django stock User admin exposes 200+ row-level permission checkboxes
plus the Groups widget plus is_staff / is_superuser flags. For TENANT
users (cashiers, owners, accountants — the people working FOR the
businesses we host), none of that machinery applies — their permissions
come from their TenantMembership.role, not from Django's row-perm system.

This admin hides the noisy machinery for tenant users, surfaces the
tenant-membership inline directly on the user change form (so operators
edit role on the same page as the user), and shows a plain-English
summary of what each role unlocks below the dropdown.

Platform-staff users (super-admin operators) still see the full Django
permission machinery — they need it to access the Django admin pages.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.accounts.permissions import (
    ROLE_DESCRIPTIONS,
    all_perms_for_role,
    role_description,
)
from apps.tenants.models import TenantMembership

from .forms import PlatformUserChangeForm
from .models import User


class TenantMembershipInline(TabularInline):
    """Edit the user's tenant memberships directly on the User form.

    Without this, super-admin operators have to bounce to
    Tenants → Tenant memberships, find the row, and edit it there.
    Most of the time the user has exactly one membership, so showing
    it inline makes the whole onboarding flow click → save on a single
    screen.

    Defaults are tuned for the 99% case (1 user = 1 tenant):
      - extra=0 → no blank "add more" rows pre-rendered. The "Add
        another Tenant membership" button is still there at the bottom
        for users who legitimately belong to multiple tenants.
      - We override get_extra() below to show ONE blank row for users
        with zero memberships (the create flow) so the operator knows
        to fill it in.
    """

    model = TenantMembership
    extra = 0  # See get_extra() below.
    max_num = 10  # Hard cap; a user with >10 tenant memberships is a
                  # red flag. The Add button still works under this limit.
    autocomplete_fields = ("tenant",)
    fields = ("tenant", "role", "is_active", "role_summary")
    readonly_fields = ("role_summary",)

    def get_extra(self, request, obj=None, **kwargs):
        """Show one blank row only when the user has no memberships
        yet (so the create flow visibly prompts for one). For an
        existing user, show only what's actually saved + the "Add
        another" button — no surprise duplicate-looking empty rows."""
        if obj and obj.memberships.exists():
            return 0
        return 1

    def get_formset(self, request, obj=None, **kwargs):
        """Inject a custom formset that rejects duplicate tenants.
        Without this, posting two rows with the same tenant raises a
        DB unique-constraint IntegrityError (which renders as a 500
        page, not a friendly form error)."""
        FormSet = super().get_formset(request, obj, **kwargs)
        original_clean = FormSet.clean

        def clean(self):
            original_clean(self)
            seen: set = set()
            for form in self.forms:
                if (
                    not form.cleaned_data
                    or form.cleaned_data.get("DELETE")
                ):
                    continue
                tenant = form.cleaned_data.get("tenant")
                if tenant is None:
                    continue
                if tenant.id in seen:
                    from django.core.exceptions import ValidationError
                    raise ValidationError(
                        f"This user already has a membership for "
                        f"{tenant.business_name}. A user can only have "
                        f"one membership per tenant — change the role "
                        f"on the existing row instead of adding a new one.",
                    )
                seen.add(tenant.id)

        FormSet.clean = clean
        return FormSet

    @admin.display(description="What this role can do")
    def role_summary(self, obj):
        """Plain-English description of the role's permissions. Updates
        when the row is saved with a new role.

        New rows (no pk yet) show a helper hint instead of a description
        since we don't know the role yet."""
        if not obj or not obj.role:
            return mark_safe(
                '<span style="opacity:0.6;font-size:11px;">'
                'Pick a role + save to see what it unlocks.</span>',
            )
        desc = role_description(obj.role)
        perms = all_perms_for_role(obj.role)
        perm_chips = "".join(
            f'<span style="display:inline-block;background:#e5e7eb;'
            f'color:#1f2937;font-family:ui-monospace,monospace;'
            f'font-size:10px;padding:1px 6px;margin:1px 3px 1px 0;'
            f'border-radius:9999px;">{p}</span>'
            for p in perms
        )
        return format_html(
            '<div style="font-size:12px;line-height:1.4;max-width:500px;">'
            '<p style="margin:0 0 6px;">{}</p>'
            '<div>{}</div>'
            '</div>',
            desc,
            mark_safe(perm_chips),
        )


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    warn_unsaved_form = True
    list_fullwidth = True
    ordering = ("email",)
    list_display = (
        "email", "full_name",
        "is_active",
        "user_type_badge",
        "membership_summary",
        "last_login",
    )
    list_filter = ("is_active", "is_platform_staff", "platform_role",
                    "preferred_language")
    search_fields = ("email", "full_name", "phone")
    inlines = [TenantMembershipInline]

    # Standard sets we use to slice the change form by user type.
    _PLATFORM_FIELDSETS = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {
            "fields": ("full_name", "phone", "preferred_language"),
        }),
        (_("Platform staff (control plane)"), {
            "fields": ("is_platform_staff", "platform_role"),
            "description": (
                "This user works for the SaaS platform, not for a "
                "tenant. They sign in at /admin/ and are blocked from "
                "every tenant API endpoint."
            ),
        }),
        (_("Platform permissions"), {
            "fields": ("is_active", "is_staff", "is_superuser",
                       "permission_bundles"),
            "description": (
                "Tick the bundles this operator needs to do their "
                "job. Each bundle grants a coherent set of view + "
                "add + change + delete permissions on related models. "
                "Cleaner than the stock Django picker, and removes "
                "the irrelevant rows (content types, JWT blacklist, "
                "etc.)."
            ),
        }),
        (_("Advanced Django permissions"), {
            "classes": ("collapse",),
            "fields": ("groups", "user_permissions"),
            "description": (
                "Power-user escape hatch. Use bundles above for the "
                "common cases. Permissions added here outside the "
                "bundles' coverage are preserved across saves."
            ),
        }),
        (_("Activity"), {
            "fields": ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until"),
        }),
    )
    _TENANT_FIELDSETS = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {
            "fields": ("full_name", "phone", "preferred_language"),
        }),
        (_("PIN"), {
            "fields": ("pin_hash",),
            "description": "Cashier's terminal-PIN for quick re-auth.",
        }),
        (_("Access"), {
            "fields": ("is_active",),
            "description": (
                "Tenant users always have is_staff=False (no Django "
                "admin access). Their actual permissions come from "
                "the tenant membership role shown below — pick a role "
                "there, save, and the user can do whatever that role "
                "allows."
            ),
        }),
        (_("Promote to platform staff"), {
            "fields": ("is_platform_staff",),
            "classes": ("collapse",),
            "description": (
                "Tick this and save to convert this account into a "
                "platform staff member (super-admin operator). After "
                "saving, the page will reload showing the platform "
                "fieldset where you can pick a platform role "
                "(super_admin / billing_admin / support_lead / etc.). "
                "Platform staff cannot access tenant APIs and any "
                "existing tenant memberships will be hidden but not "
                "deleted."
            ),
        }),
        (_("Activity"), {
            "fields": ("last_login", "password_changed_at",
                       "failed_login_count", "locked_until"),
        }),
    )

    # Add (create) form — minimal but lets the operator decide between
    # tenant user vs platform-staff at creation time. Two paths:
    #
    #   Default (is_platform_staff unticked):
    #     → creates a TENANT user. After saving, page reloads with
    #       the tenant fieldset + a Tenant memberships inline. Add
    #       a membership there to grant access to a specific tenant.
    #
    #   is_platform_staff ticked:
    #     → creates a PLATFORM-STAFF user. After saving, page reloads
    #       with the platform fieldset where you pick the platform
    #       role (super_admin / billing_admin / support_lead / etc.).
    #       No tenant membership inline (platform staff don't belong
    #       to tenants).
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "password1", "password2",
                       "is_active", "is_platform_staff"),
            "description": (
                "Leave 'Is platform staff' unticked for a tenant user "
                "(cashier / manager / owner of a business). Tick it "
                "for a super-admin / platform operator. After saving, "
                "the page reloads with role-specific fields."
            ),
        }),
    )

    readonly_fields = (
        "last_login", "password_changed_at", "pin_hash",
        "failed_login_count", "locked_until",
    )

    def get_fieldsets(self, request, obj=None):
        """Use the platform fieldset for platform-staff users, the
        tenant fieldset for everyone else. New users (obj is None)
        go through add_fieldsets via Django's base class."""
        if obj is None:
            return self.add_fieldsets
        if obj.is_platform_staff or obj.is_superuser:
            return self._PLATFORM_FIELDSETS
        return self._TENANT_FIELDSETS

    def get_form(self, request, obj=None, change=False, **kwargs):
        """Swap the form when editing a platform-staff user so we get
        the curated permission_bundles field. Tenant users (and the
        add form) keep the stock UserChangeForm — they don't have
        permission_bundles.

        Pass `request.user` into the form so it can enforce the
        delegation rule (operator can only grant bundles they hold).
        """
        if change and obj is not None and (obj.is_platform_staff or obj.is_superuser):
            kwargs["form"] = PlatformUserChangeForm
            FormCls = super().get_form(request, obj, change=change, **kwargs)

            # Wrap the form class so its __init__ receives request_user.
            class _BoundForm(FormCls):
                def __init__(self, *args, **inner_kwargs):
                    inner_kwargs["request_user"] = request.user
                    super().__init__(*args, **inner_kwargs)

            return _BoundForm
        return super().get_form(request, obj, change=change, **kwargs)

    # App labels we ALWAYS hide from both the bundles' allow-list and
    # the advanced user_permissions widget — Django plumbing + JWT
    # internals + materialized report tables. Editing these via the
    # admin is at best useless, at worst dangerous (breaks auth).
    _HIDDEN_APP_LABELS = frozenset({
        "contenttypes",         # Django internal model registry
        "token_blacklist",      # JWT blacklist + outstanding tokens
        "admin",                # Django admin LogEntry
        "sessions",             # Web session rows
    })
    # Models whose rows are computed / append-only — editing perms on
    # them is misleading. Hide from the advanced widget too.
    _HIDDEN_MODELS = frozenset({
        ("reports", "dailysalessummary"),
        ("reports", "productvelocity"),
        ("reports", "reportrun"),
        ("reports", "reportfavorite"),
        ("sync", "synclog"),
        ("customers", "customerledger"),
        ("sales", "saleitemhistory"),
        ("auth", "permission"),     # editing Permission rows themselves
    })

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """Filter the user_permissions queryset to drop the plumbing /
        dangerous rows even in the advanced expandable section."""
        if db_field.name == "user_permissions":
            qs = kwargs.get("queryset") or db_field.remote_field.model.objects
            qs = qs.exclude(content_type__app_label__in=self._HIDDEN_APP_LABELS)
            for app_label, model_name in self._HIDDEN_MODELS:
                qs = qs.exclude(
                    content_type__app_label=app_label,
                    content_type__model=model_name,
                )
            kwargs["queryset"] = qs.select_related("content_type")
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        """Hide the tenant-membership inline on the create form
        (the user doesn't have a pk yet, so the inline would fail
        to save) and on platform-staff users (they shouldn't have
        any memberships).
        """
        if obj is None or obj.is_platform_staff:
            return []
        return super().get_inline_instances(request, obj)

    # ------------------------------------------------------------------
    # Two-tier admin hierarchy enforcement
    #
    # Tier 1 — Super super admin (request.user.is_superuser=True)
    #   Full CRUD on all users including other super admins.
    #
    # Tier 2 — Super admins / platform staff (is_platform_staff=True)
    #   Can add new users. Cannot edit OR delete platform-staff peers
    #   (other super admins), even if they hold the User management
    #   bundle. They can edit their own profile (password, name).
    #
    # Tier 3 — Tenant users
    #   These checks aren't relevant — tenant users don't access
    #   /admin/ at all (is_staff=False). The middleware bounces them.
    # ------------------------------------------------------------------

    def has_change_permission(self, request, obj=None):
        # Base check (does the user have accounts.change_user at all?)
        # — if no, deny early. is_superuser bypasses everything.
        if not super().has_change_permission(request, obj):
            return False
        # Without a specific object, we're rendering the changelist —
        # show it; per-row filtering happens when an operator clicks
        # into a specific row.
        if obj is None:
            return True
        # Super super admin: unrestricted.
        if request.user.is_superuser:
            return True
        # Anyone may edit their own profile (password reset, name change).
        if obj.pk == request.user.pk:
            return True
        # Rule 2 (strict): non-superusers cannot change ANY existing
        # user. Only Add is allowed. Self-edit covered above.
        return False

    def has_delete_permission(self, request, obj=None):
        # Only the super super admin can delete users. Rule 2.
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    # ------------------------------------------------------------------
    # Safe delete — surface the User.delete() guard as a friendly admin
    # error instead of letting it bubble to a 500. The guard refuses to
    # delete a user who is the last active owner of any tenant.
    # ------------------------------------------------------------------

    def delete_model(self, request, obj):
        """Single-row delete via the change form. Catch the model
        guard's ValidationError and surface it as an admin message.
        Without this, the operator sees a server-error page with no
        explanation of why the delete refused."""
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        try:
            super().delete_model(request, obj)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
            messages.error(request, msg)
            # Re-raise so Django's flow knows not to redirect with a
            # success message. The view machinery converts this back
            # into a friendly page render.
            raise

    def delete_queryset(self, request, queryset):
        """Bulk-delete action. Tries each user one by one so a single
        last-owner row doesn't kill the whole batch — every problem
        user gets a clear message; everyone else gets deleted."""
        from django.contrib import messages
        from django.core.exceptions import ValidationError

        blocked: list[str] = []
        deleted = 0
        for user in queryset:
            try:
                user.delete()
                deleted += 1
            except ValidationError as e:
                msg = e.message if hasattr(e, "message") else "; ".join(e.messages)
                blocked.append(f"{user.email}: {msg}")

        if deleted:
            messages.success(
                request,
                f"Deleted {deleted} user{'s' if deleted != 1 else ''}.",
            )
        for line in blocked:
            messages.error(request, line)

    def get_deleted_objects(self, objs, request):
        """Hook into the delete-confirmation page rendering.

        Django's standard page lists what will cascade (memberships,
        notifications, etc.). We additionally inject a prominent
        warning for users who are the last owner of a tenant — so
        the operator sees the problem BEFORE clicking confirm, not
        after.
        """
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request,
        )

        warnings: list[str] = []
        for obj in objs:
            if isinstance(obj, User):
                last_owner_of = list(obj.tenants_where_last_active_owner())
                if last_owner_of:
                    names = ", ".join(t.business_name for t in last_owner_of)
                    warnings.append(
                        f"⚠ {obj.email} is the only active owner of: "
                        f"{names}. Deleting will orphan "
                        f"{'these tenants' if len(last_owner_of) > 1 else 'this tenant'}. "
                        f"Promote another member to owner first.",
                    )
        if warnings:
            # Prepend our warnings to the deleted list so they appear
            # at the top of the confirmation page, where the operator
            # actually reads them.
            from django.utils.safestring import mark_safe
            from django.utils.html import format_html
            warning_html = format_html(
                '<ul style="background:#fef2f2;border:1px solid #fca5a5;'
                'border-radius:6px;padding:12px 16px;margin:0 0 12px;'
                'color:#991b1b;list-style:none;">{}</ul>',
                mark_safe("".join(
                    f'<li style="margin:4px 0;">{w}</li>' for w in warnings
                )),
            )
            deleted = [warning_html] + list(deleted)

        return deleted, model_count, perms_needed, protected

    # ----- List display helpers ---------------------------------------

    @admin.display(description="Type / role", ordering="is_platform_staff")
    def user_type_badge(self, obj):
        """Surface the user's tier at a glance:
          - Super super admin (is_superuser=True) → red 'Super admin' pill
          - Platform staff → purple pill + platform_role label
          - Tenant user → green pill (membership column carries the role)
        """
        # Tier 1 — the super super admin.
        if obj.is_superuser:
            return format_html(
                '<span style="background:#dc2626;color:white;'
                'padding:2px 8px;border-radius:9999px;font-size:11px;'
                'font-weight:600;" title="Super super admin — '
                'unrestricted access">Super admin</span>',
            )
        # Tier 2 — platform staff. Show the platform_role label when set.
        if obj.is_platform_staff:
            role_label = (
                obj.get_platform_role_display() if obj.platform_role
                else "Platform staff"
            )
            return format_html(
                '<span style="background:#7c3aed;color:white;'
                'padding:2px 8px;border-radius:9999px;font-size:11px;'
                'font-weight:600;" title="Platform staff — {}">{}</span>',
                obj.platform_role or "no role assigned",
                role_label,
            )
        # Tier 3 — tenant user.
        return format_html(
            '<span style="background:#16a34a;color:white;'
            'padding:2px 8px;border-radius:9999px;font-size:11px;'
            'font-weight:600;">Tenant user</span>',
        )

    @admin.display(description="Permissions / tenants")
    def membership_summary(self, obj):
        """Two different summaries depending on user tier:
          - Platform staff → chip list of bundle keys they HOLD
            (derived live from user_permissions). Lets operators see
            at a glance which bundles each staff member has.
          - Tenant user → list of their active TenantMembership rows
            (tenant name + role). Catches 'forgot to add membership'
            with a red warning when empty.
        """
        # ---- Platform staff: show held bundles ----
        if obj.is_platform_staff:
            # Defer import so the admin module doesn't pull this at load.
            from .platform_perms import (
                PLATFORM_PERMISSION_BUNDLES,
                bundle_perm_keys,
            )

            # Super super admin holds everything by definition.
            if obj.is_superuser:
                return format_html(
                    '<span style="background:#fef3c7;color:#92400e;'
                    'padding:2px 8px;border-radius:9999px;font-size:11px;'
                    'font-weight:600;" title="Super super admin has '
                    'full CRUD on every model">All bundles (super)</span>',
                )

            # Derive which bundles the user fully holds.
            held_pairs = {
                (p.content_type.app_label, p.codename)
                for p in obj.user_permissions.select_related("content_type")
            }
            held_bundles = [
                b for b in PLATFORM_PERMISSION_BUNDLES
                if bundle_perm_keys(b["key"]).issubset(held_pairs)
            ]
            if not held_bundles:
                return format_html(
                    '<span style="color:#dc2626;font-size:11px;">'
                    '⚠ no bundles assigned</span>',
                )
            return format_html_join(
                mark_safe(" "),
                '<span style="display:inline-block;background:#ede9fe;'
                'color:#5b21b6;font-size:10px;padding:1px 6px;'
                'border-radius:9999px;font-weight:500;margin:1px 2px;" '
                'title="{}">{}</span>',
                ((b["description"], b["label"]) for b in held_bundles),
            )

        # ---- Tenant user: show tenant memberships ----
        memberships = list(
            TenantMembership.objects.filter(user=obj, is_active=True)
            .select_related("tenant")
            .order_by("tenant__business_name")
        )
        if not memberships:
            return format_html(
                '<span style="color:#dc2626;font-size:11px;">'
                '⚠ no active membership</span>',
            )
        return format_html_join(
            mark_safe("<br>"),
            '<span style="font-size:12px;"><strong>{}</strong> '
            '<em style="opacity:0.7;">({})</em></span>',
            ((m.tenant.business_name, m.role) for m in memberships),
        )
