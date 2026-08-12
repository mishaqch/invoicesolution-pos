"""Tax report (FBR-format).

Reports tax collected per rate-band per period — the same shape used in
the PRAL Annexure-C wire format. Drivers off SaleItem so partial cancel
flips reflect correctly (cancelled rows excluded).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Sum

from apps.sales.models import SaleItem

from ..aggregates import COUNTED_SALES_STATUSES
from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    pass


@register
class TaxReport(Report):
    name = "tax"
    Filters = _Filters
    columns = (
        Column("tax_rate", "Rate %", "decimal", "right"),
        Column("line_count", "Lines", "int", "right"),
        Column("taxable_value", "Taxable value", "money", "right"),
        Column("tax_amount", "Tax", "money", "right"),
    )

    def query(self):
        # Exclude fully-cancelled invoices: a portal-reconcile cancel flips the
        # invoice status but not each item's is_cancelled, so gating on the
        # non-cancelled status set keeps that invoice's tax out of the base.
        qs = SaleItem.objects.filter(
            invoice__tenant_id=self.tenant_id,
            invoice__status__in=COUNTED_SALES_STATUSES,
            is_cancelled=False,
        )
        if self.filters.branch_id:
            qs = qs.filter(invoice__branch_id=self.filters.branch_id)
        if self.filters.date_from:
            qs = qs.filter(invoice__invoice_date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(invoice__invoice_date__lte=self.filters.date_to)
        rows = (
            qs.values("tax_rate")
            .annotate(
                line_count=Count("id"),
                taxable_value=Sum("line_total") - Sum("tax_amount"),
                tax_amount=Sum("tax_amount"),
            )
            .order_by("tax_rate")
        )
        for r in rows:
            yield {
                "tax_rate": r["tax_rate"],
                "line_count": r["line_count"],
                "taxable_value": r["taxable_value"] or Decimal("0"),
                "tax_amount": r["tax_amount"] or Decimal("0"),
            }
