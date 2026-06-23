"""Global 2-decimal rendering for money/quantity in the Django super-admin.

Money and quantity are stored as DecimalField(max_digits=14, decimal_places=4),
so Django's admin renders them as "500.0000" in both changelists and readonly
detail views. Shopkeepers expect "500.00".

We patch `django.contrib.admin.utils.display_for_field` — the single function
Django uses to format a model field's value in BOTH the changelist
(templatetags.admin_list) and the readonly detail form (admin.helpers). For a
4-dp DecimalField we render the value at 2 dp with thousands separators; every
other field type falls through to Django's original behaviour unchanged.

Because `helpers` and `admin_list` import the function by NAME at module load,
we rebind it on all three modules, not just the canonical one.

Applied once from PlatformAdminConfig.ready(). Idempotent (guarded), display
only — the stored Decimal(4dp) is untouched, so tax math and FBR payloads are
unaffected.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField


def _install() -> None:
    from django.contrib.admin import utils as admin_utils

    # Guard against double-patching (ready() can run more than once in tests).
    if getattr(admin_utils.display_for_field, "_ivs_2dp", False):
        return

    original = admin_utils.display_for_field

    def display_for_field(value, field, empty_value_display):
        # Only reshape 4-dp Decimal money/quantity fields; everything else is
        # Django's job. NULLs fall through so "—"/empty handling stays Django's.
        if (
            isinstance(field, DecimalField)
            and field.decimal_places == 4
            and value is not None
            and value != ""
        ):
            try:
                n = Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                return original(value, field, empty_value_display)
            # 2 dp, en-US style thousands separators (matches admin-web money()).
            return f"{n:,.2f}"
        return original(value, field, empty_value_display)

    display_for_field._ivs_2dp = True  # type: ignore[attr-defined]

    # Rebind on every module that holds a reference to the original.
    admin_utils.display_for_field = display_for_field
    from django.contrib.admin import helpers as admin_helpers
    from django.contrib.admin.templatetags import admin_list

    admin_helpers.display_for_field = display_for_field
    admin_list.display_for_field = display_for_field
