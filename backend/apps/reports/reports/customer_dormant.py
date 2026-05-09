"""Customer dormant — customers with no invoice in N days but who used to spend."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Max, Sum
from django.utils import timezone

from apps.customers.models import Customer
from apps.sales.models import Invoice

from ..aggregates import COUNTED_STATUSES
from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    dormant_days: int = 60
    min_lifetime_spent: str = "0"


@register
class CustomerDormantReport(Report):
    name = "customer_dormant"
    Filters = _Filters
    columns = (
        Column("name", "Customer"),
        Column("phone", "Phone"),
        Column("last_invoice_at", "Last visit", "date"),
        Column("days_since", "Days dormant", "int", "right"),
        Column("lifetime_spent", "Lifetime spent", "money", "right"),
    )

    def query(self):
        cutoff = (timezone.localdate() - dt.timedelta(days=self.filters.dormant_days))
        # Lifetime spend per customer.
        spent = (
            Invoice.objects.for_tenant(self.tenant_id)
            .filter(status__in=COUNTED_STATUSES, customer__isnull=False)
            .values("customer_id")
            .annotate(
                last_invoice_at=Max("invoice_date"),
                lifetime_spent=Sum("grand_total"),
                visit_count=Count("id"),
            )
        )
        min_spent = Decimal(self.filters.min_lifetime_spent)
        candidates = [
            s for s in spent
            if s["last_invoice_at"]
            and s["last_invoice_at"] <= cutoff
            and (s["lifetime_spent"] or Decimal("0")) >= min_spent
        ]
        candidates.sort(key=lambda r: r["lifetime_spent"] or Decimal("0"), reverse=True)
        cust_ids = [c["customer_id"] for c in candidates]
        cust_map = {
            c.id: c for c in Customer.objects.filter(id__in=cust_ids).only("id", "name", "phone")
        }
        today = timezone.localdate()
        for c in candidates:
            cu = cust_map.get(c["customer_id"])
            yield {
                "name": cu.name if cu else "(deleted)",
                "phone": (cu.phone if cu else "") or "",
                "last_invoice_at": c["last_invoice_at"],
                "days_since": (today - c["last_invoice_at"]).days,
                "lifetime_spent": c["lifetime_spent"] or Decimal("0"),
            }
