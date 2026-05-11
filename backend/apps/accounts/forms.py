"""Custom admin form for platform-staff User instances.

Replaces the stock `user_permissions` widget (200-permission picker)
with a curated bundle-checkbox field. See apps.accounts.platform_perms
for the bundle catalog.

The bundle field stores transient state on the form; on save we
translate it into the underlying auth.Permission rows. Existing users
get their checkboxes pre-ticked by the reverse lookup
(`bundle_for_permission`).
"""

from __future__ import annotations

from django import forms
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from unfold.forms import UserChangeForm as UnfoldUserChangeForm

from .platform_perms import (
    PLATFORM_PERMISSION_BUNDLES,
    all_bundle_perm_keys,
    bundle_for_permission,
    bundle_perm_keys,
)


def _bundles_editor_can_grant(editor) -> set[str]:
    """Which bundles is `editor` allowed to grant to other users?

    Rules:
      - Superuser (is_superuser=True): all bundles.
      - Non-superuser platform staff: only bundles whose underlying
        permissions they hold themselves. Granting more than that
        would be privilege escalation.
      - None / anonymous: empty set (form rendered without bundles —
        the requesting user obviously can't manage other users anyway,
        Django's has_change_permission catches this earlier).
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
    """Renders the bundle list with description + label per checkbox.

    Pre-resolves the catalog + checked state in get_context() so the
    template stays trivial — Django's stock CheckboxSelectMultiple
    optgroups context is awkward to consume when we want to display
    extra metadata (descriptions) alongside the choices.
    """

    template_name = "accounts/admin/permission_bundles.html"

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)

        # Normalize the field value to a set of strings. The widget
        # receives either:
        #   - the raw cleaned_data list (on POST re-render)
        #   - the field's initial list (on GET)
        #   - None (rare; treat as empty)
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


class PlatformUserChangeForm(UnfoldUserChangeForm):
    """The User change form rendered for platform-staff users.

    Adds `permission_bundles` (the new curated picker) and removes
    the stock `user_permissions` widget from operator view. The
    underlying Permission rows are still what gets saved — the bundle
    field is purely a UI layer.

    Delegation safety: a non-superuser editing this form can only
    grant bundles they themselves hold. This prevents a delegated
    support_lead from elevating a fellow operator to super-admin
    just because they have the User management bundle. Superusers
    (e.g. ch.m.ishaq@gmail.com) bypass the check.
    """

    permission_bundles = forms.MultipleChoiceField(
        required=False,
        widget=PermissionBundleWidget,
        choices=[],  # populated in __init__
        label="Platform permissions",
        help_text=(
            "Tick the bundles this operator needs. Each bundle grants "
            "view/add/change/delete on a set of related models. To "
            "see the underlying Django permissions, expand 'Advanced "
            "Django permissions' below."
        ),
    )

    class Meta(UnfoldUserChangeForm.Meta):
        # Explicitly EXCLUDE the legacy AbstractUser fields that don't
        # exist on our custom User model. Django's UserChangeForm
        # auto-includes `username` + `date_joined` from AbstractUser
        # which our admin's fieldsets correctly don't render — but
        # Django still considers them required at validation time.
        # Exclude them so the form's required-fields list matches what
        # the fieldsets actually render.
        exclude = ("username", "date_joined", "last_login")

    def __init__(self, *args, **kwargs):
        # The admin passes the requesting user via the form's kwargs in
        # newer Django versions via get_form(). We pop it so the parent
        # constructor doesn't choke on an unknown kwarg.
        self._request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)

        # Build the choice list from the catalog, filtered by what the
        # requesting user is allowed to grant (delegation safety).
        editor_allowed = _bundles_editor_can_grant(self._request_user)
        self.fields["permission_bundles"].choices = [
            (b["key"], b["label"])
            for b in PLATFORM_PERMISSION_BUNDLES
            if b["key"] in editor_allowed
        ]
        # Catalog passed to widget filtered to the same set so the
        # template doesn't show cards the operator can't toggle.
        self.fields["permission_bundles"].widget.attrs["bundles"] = [
            b for b in PLATFORM_PERMISSION_BUNDLES
            if b["key"] in editor_allowed
        ]

        # Pre-tick bundles that match the user's current permissions.
        # An existing user with explicit perms across multiple bundles
        # ends up with multiple ticks — exactly right.
        if self.instance and self.instance.pk:
            current_bundles: set[str] = set()
            user_perms = self.instance.user_permissions.select_related(
                "content_type"
            ).all()
            for p in user_perms:
                bkey = bundle_for_permission(
                    p.content_type.app_label, p.codename,
                )
                if bkey:
                    current_bundles.add(bkey)
            self.fields["permission_bundles"].initial = list(current_bundles)

    def _save_m2m(self):
        """Translate ticked bundles back into user_permissions, ON TOP
        of what the stock ModelForm M2M save has written.

        Django's admin flow:
          1. form.save(commit=False)        → returns instance
          2. form.instance.save()           → persists instance
          3. form.save_m2m()                → writes M2M fields
                                              (user_permissions, groups)

        If we did this work inside save() (i.e. step 1/2), the M2M
        write in step 3 would overwrite ours — the regular
        user_permissions field was empty in the form, so save_m2m()
        called .set([]) and wiped everything we just set.

        Hooking _save_m2m() means we run AFTER the stock M2M save, so
        we get the final word.
        """
        super()._save_m2m()
        if not self.instance.pk:
            return

        user = self.instance
        ticked_bundles: list[str] = list(
            self.cleaned_data.get("permission_bundles") or []
        )

        # Compute target (app_label, codename) set from ticked bundles.
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

        # Preserve any user_permissions OUTSIDE the bundle universe —
        # operator may have added them via the advanced widget. Read
        # the current set AFTER super()._save_m2m() so we see the
        # advanced widget's chosen perms too.
        all_bundle_pairs = all_bundle_perm_keys()
        current_perms = user.user_permissions.select_related("content_type").all()
        outside_bundle_perms = [
            p for p in current_perms
            if (p.content_type.app_label, p.codename) not in all_bundle_pairs
        ]

        # Final set = bundle perms (per ticks) ∪ non-bundle perms.
        final_perm_pks = list(
            {p.pk for p in new_bundle_perms + outside_bundle_perms}
        )
        user.user_permissions.set(final_perm_pks)
