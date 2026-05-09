"""Cashier performance — invoices, gross, avg ticket, refunds per cashier."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Avg, Count, Sum

from apps.sales.models import Invoice

from ..aggregates import COUNTED_STATUSES
from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class CashierPerformanceReport(Report):
    name = "cashier_performance"
    Filters = _Filters
    columns = (
        Column("cashier_email", "Cashier"),
        Column("invoice_count", "Invoices", "int", "right"),
        Column("gross", "Gross", "money", "right"),
        Column("avg_ticket", "Avg ticket", "money", "right"),
    )

    def query(self):
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
            qs.values("cashier_id", "cashier__email")
            .annotate(
                invoice_count=Count("id"),
                gross=Sum("grand_total"),
                avg_ticket=Avg("grand_total"),
            )
            .order_by("-gross")
        )
        for r in rows:
            yield {
                "cashier_email": r["cashier__email"] or "(unknown)",
                "invoice_count": r["invoice_count"],
                "gross": r["gross"] or Decimal("0"),
                "avg_ticket": r["avg_ticket"] or Decimal("0"),
            }
