"""On-demand aggregate refresh mixins for aggregate-backed reports.

Reports that read a snapshot table (daily_sales_summary, product_velocity)
must not depend on the Celery beat task having run — otherwise a freshly
activated tenant, or a tenant whose beat schedule lagged, sees an empty
report even though the underlying invoices exist. Each mixin recomputes its
snapshot for the report's filter window on demand (idempotent), then the
report reads the just-refreshed rows.

The window defaults to the trailing year when the caller supplies no dates,
which bounds the recompute cost while covering every realistic "all time"
report view.
"""

from __future__ import annotations

import datetime as _dt

from apps.tenants.models import Tenant

from .daily_sales import rebuild_daily_sales
from .product_velocity import rebuild_product_velocity

# Trailing window used when a report is run with no explicit date range.
_DEFAULT_SPAN_DAYS = 365


def _resolve_window(filters) -> tuple[_dt.date, _dt.date]:
    today = _dt.date.today()
    date_from = filters.date_from or (today - _dt.timedelta(days=_DEFAULT_SPAN_DAYS))
    date_to = filters.date_to or today
    if isinstance(date_from, str):
        date_from = _dt.date.fromisoformat(date_from)
    if isinstance(date_to, str):
        date_to = _dt.date.fromisoformat(date_to)
    return date_from, date_to


class _EnsuresAggregate:
    """Base for the two mixins. Subclasses set `_rebuild`."""

    _rebuild = None  # set by subclass

    def _ensure_aggregate(self) -> None:
        tenant = Tenant.objects.filter(pk=self.tenant_id).first()
        if tenant is None:
            return
        date_from, date_to = _resolve_window(self.filters)
        try:
            type(self)._rebuild(tenant, date_from=date_from, date_to=date_to)
        except Exception:
            # A recompute hiccup must never break the report read — fall back to
            # whatever the last snapshot held.
            pass


class EnsuresDailySales(_EnsuresAggregate):
    _rebuild = staticmethod(rebuild_daily_sales)


class EnsuresProductVelocity(_EnsuresAggregate):
    _rebuild = staticmethod(rebuild_product_velocity)
