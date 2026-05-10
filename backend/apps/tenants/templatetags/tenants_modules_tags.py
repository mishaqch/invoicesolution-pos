"""Template tags for the modules-checkbox widget.

`grouped_modules` joins the widget's currently-selected values with the
catalog metadata so the template can render a real grouped checklist
(stock CheckboxSelectMultiple gives only key/label tuples).
"""

from __future__ import annotations

from django import template

from apps.tenants.modules import FORCED_MODULE_KEYS, MODULES

register = template.Library()


@register.filter
def grouped_modules(widget):
    """Return a list of catalog dicts augmented with `checked` booleans.

    The template uses {% regroup ... by group %} to bucket them by the
    group field; each entry exposes key, label, group, description,
    forced, and checked.
    """
    selected = set(widget.get("value") or [])
    return [
        {
            **m,
            "checked": m["key"] in selected,
            # Forced ones must always render as checked even if the
            # underlying value somehow excluded them.
            "forced": m["key"] in FORCED_MODULE_KEYS,
        }
        for m in MODULES
    ]
