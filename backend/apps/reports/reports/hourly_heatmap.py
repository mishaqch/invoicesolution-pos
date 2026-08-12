"""Hourly sales heatmap — count + gross by hour of day, dow.

Pulls directly from invoices since the aggregate is daily. We group by
PKT hour-of-day; the dataset is small (24 buckets × 7 weekdays).
"""

from __future__ import annotations

import zoneinfo
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay

from apps.sales.models import Invoice

from ..aggregates import COUNTED_STATUSES
from ..base import BaseFilters, ChartSpec, Column, Report
from ..registry import register

# ExtractWeekDay: 1=Sunday .. 7=Saturday (Postgres/Django convention).
_WEEKDAY_NAMES = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}


@dataclass
class _Filters(BaseFilters):
    pass


@register
class HourlyHeatmapReport(Report):
    name = "hourly_heatmap"
    Filters = _Filters
    columns = (
        Column("weekday", "Weekday", "text"),
        Column("hour", "Hour", "int", "right"),
        Column("count", "Invoices", "int", "right"),
        Column("gross", "Gross", "money", "right"),
    )
    chart_spec = ChartSpec(type="heatmap", x_key="hour", y_keys=("weekday", "count"))

    def query(self):
        # Bucket by PAKISTAN local time deterministically — ExtractHour without
        # an explicit tz uses the active tz, which falls back to UTC in Celery
        # runs and would shift every bucket 5 hours. Weekday is derived from the
        # SAME created_at timestamp so hour + weekday agree.
        pk_tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
        qs = Invoice.objects.for_tenant(self.tenant_id).filter(
            status__in=COUNTED_STATUSES,
        )
        if self.filters.branch_id:
            qs = qs.filter(branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(invoice_date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(invoice_date__lte=self.filters.date_to)
        rows = (
            qs.annotate(
                hour=ExtractHour("created_at", tzinfo=pk_tz),
                weekday=ExtractWeekDay("created_at", tzinfo=pk_tz),
            )
            .values("weekday", "hour")
            .annotate(count=Count("id"), gross=Sum("grand_total"))
            .order_by("weekday", "hour")
        )
        for r in rows:
            yield {
                "weekday": _WEEKDAY_NAMES.get(r["weekday"], str(r["weekday"])),
                "hour": r["hour"],
                "count": r["count"],
                "gross": r["gross"] or Decimal("0"),
            }
