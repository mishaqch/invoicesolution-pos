"""Rebuild product_velocity for a (tenant, date) range.

Source: SaleItem rows joined to their Invoice for branch + invoice_date,
filtered by counted statuses (same set as daily_sales).

We aggregate in two passes: SUM(quantity), SUM(line_total) via the ORM,
plus a separate SUM(quantity*cost_price) using raw SQL for the COGS
column (Django's aggregate planner refuses to combine arithmetic on
two fields with GROUP BY in one call).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import F, Sum

from apps.sales.models import SaleItem
from apps.tenants.models import Tenant

from ..models import ProductVelocity
# Revenue/margin reports must EXCLUDE fully-cancelled invoices (they'd inflate
# a product's revenue + COGS), so this aggregate uses the narrower sales set.
from .daily_sales import COUNTED_SALES_STATUSES


@transaction.atomic
def rebuild_product_velocity(tenant: Tenant, *, date_from: dt.date, date_to: dt.date) -> int:
    items = (
        SaleItem.objects
        .filter(
            invoice__tenant=tenant,
            invoice__invoice_date__gte=date_from,
            invoice__invoice_date__lte=date_to,
            invoice__status__in=COUNTED_SALES_STATUSES,
            is_cancelled=False,
        )
        .values(
            "product_id",
            branch_id=F("invoice__branch_id"),
            date=F("invoice__invoice_date"),
        )
        .annotate(
            quantity=Sum("quantity"),
            revenue=Sum("line_total"),                       # gross (tax-inclusive)
            # net = line_total − output tax − further tax (tax-exclusive).
            net_revenue=Sum(F("line_total") - F("tax_amount") - F("further_tax_amount")),
        )
    )

    cogs_map = _cogs_per_group(tenant, date_from=date_from, date_to=date_to)

    upserted = 0
    for row in items:
        key = (row["product_id"], row["branch_id"], row["date"])
        ProductVelocity.objects.update_or_create(
            tenant=tenant,
            product_id=row["product_id"],
            branch_id=row["branch_id"],
            date=row["date"],
            defaults={
                "quantity": row["quantity"] or Decimal("0"),
                "revenue": row["revenue"] or Decimal("0"),
                "net_revenue": row["net_revenue"] or Decimal("0"),
                "cogs": cogs_map.get(key, Decimal("0")),
            },
        )
        upserted += 1
    return upserted


def _cogs_per_group(tenant: Tenant, *, date_from: dt.date, date_to: dt.date) -> dict:
    """SUM(quantity * cost_price) per (product, branch, date) via raw SQL.

    The ORM refuses to aggregate field-arithmetic combined with GROUP BY in
    one call, so we drop to SQL for this single column.
    """
    sql = """
        SELECT
          si.product_id,
          inv.branch_id,
          inv.invoice_date,
          -- COALESCE: services / room folio lines have NULL cost_price; a NULL
          -- here would zero the whole group's COGS and inflate margin.
          SUM(si.quantity * COALESCE(si.cost_price, 0)) AS cogs
        FROM sale_items si
        JOIN invoices inv ON inv.id = si.invoice_id
        WHERE inv.tenant_id = %s
          AND inv.invoice_date >= %s
          AND inv.invoice_date <= %s
          AND inv.status = ANY(%s)
          AND si.is_cancelled = FALSE
        GROUP BY si.product_id, inv.branch_id, inv.invoice_date
    """
    out: dict = {}
    with connection.cursor() as cur:
        cur.execute(sql, [str(tenant.id), date_from, date_to, list(COUNTED_SALES_STATUSES)])
        for product_id, branch_id, date, cogs in cur.fetchall():
            out[(product_id, branch_id, date)] = cogs or Decimal("0")
    return out
