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
        super().__init__(*args, **kwargs)

        # Build the choice list from the catalog. Choice values are
        # bundle keys; choice labels are the operator-facing label.
        # The custom template uses widget.attrs["bundles"] to render
        # description + label per option.
        self.fields["permission_bundles"].choices = [
            (b["key"], b["label"]) for b in PLATFORM_PERMISSION_BUNDLES
        ]
        # Stash the catalog on the widget so the template can render
        # descriptions alongside each checkbox.
        self.fields["permission_bundles"].widget.attrs["bundles"] = (
            PLATFORM_PERMISSION_BUNDLES
        )

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

    def save(self, commit: bool = True):
        """Translate ticked bundles back into the user_permissions M2M.

        Strategy:
          1. Save the User instance first (so it has a pk + M2M
             through table exists).
          2. Compute the target permission set from the ticked bundles.
          3. SET (not add) the user's permissions to that set — we
             want a clean replace so unticking a bundle removes the
             matching perms.
          4. Any user_permissions OUTSIDE the bundle universe stay
             untouched (operator edited them in the advanced widget).
        """
        user = super().save(commit=commit)
        if not commit:
            return user

        ticked_bundles: list[str] = list(
            self.cleaned_data.get("permission_bundles") or []
        )

        # Compute target (app_label, codename) set from ticked bundles.
        target_pairs: set[tuple[str, str]] = set()
        for b in ticked_bundles:
            target_pairs |= bundle_perm_keys(b)

        # Resolve to Permission row pks.
        if target_pairs:
            # Group codenames by app_label for efficient querying.
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

        # Find which CURRENT perms come from bundles (so we know which
        # to remove on save) and which are outside the bundle universe
        # (operator added via advanced widget — preserve them).
        all_bundle_pairs = all_bundle_perm_keys()
        current_perms = user.user_permissions.select_related("content_type").all()
        outside_bundle_perms = [
            p for p in current_perms
            if (p.content_type.app_label, p.codename) not in all_bundle_pairs
        ]

        # Final set = perms inside bundles (per ticks) + perms outside bundles.
        final_perms = list({p.pk for p in new_bundle_perms + outside_bundle_perms})
        user.user_permissions.set(final_perms)
        return user
