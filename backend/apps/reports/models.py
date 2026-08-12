"""Reports persistence — favorites, async report runs, materialized aggregates.

The aggregate tables are not Django-managed in the strict sense (they
are rebuilt by Celery beat) but having them as Django models keeps
queries idiomatic and tenant-scoping enforced via the standard manager.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


# ---------------------------------------------------------------------------
# Saved filter favorites
# ---------------------------------------------------------------------------


class ReportFavorite(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="report_favorites",
    )
    report_name = models.CharField(max_length=64)
    label = models.CharField(max_length=128)
    filters_json = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "user", "report_name"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "report_name", "label"],
                name="report_favorite_unique_label",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_name}:{self.label}"


# ---------------------------------------------------------------------------
# Async report runs
# ---------------------------------------------------------------------------


REPORT_RUN_STATUS = (
    ("queued", "Queued"),
    ("running", "Running"),
    ("ready", "Ready"),
    ("failed", "Failed"),
)


class ReportRun(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="report_runs",
    )
    report_name = models.CharField(max_length=64)
    filters_json = models.JSONField(default=dict)
    export_format = models.CharField(
        max_length=8, choices=[("csv", "csv"), ("xlsx", "xlsx"), ("pdf", "pdf")],
        blank=True, default="",
    )
    status = models.CharField(max_length=12, choices=REPORT_RUN_STATUS, default="queued")
    error = models.TextField(blank=True, default="")
    output_path = models.CharField(max_length=512, blank=True, default="")
    row_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "user", "-created_at"]),
            models.Index(fields=["tenant", "status"]),
        ]


# ---------------------------------------------------------------------------
# Materialized aggregates — rebuilt by Celery beat
# ---------------------------------------------------------------------------


class DailySalesSummary(TenantScopedModel):
    """One row per (tenant, branch, date). Source for daily/hourly/branch
    reports + dashboard KPIs.

    'gross' = sum of grand_total on valid invoices
    'net'   = gross - tax
    'count' = count of valid invoices
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    branch = models.ForeignKey("tenants.Branch", on_delete=models.CASCADE)
    date = models.DateField()
    gross = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    net = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    invoice_count = models.PositiveIntegerField(default=0)
    refund_count = models.PositiveIntegerField(default=0)
    refund_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    last_built_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "date"],
                name="dailysales_uniq_per_branch_day",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "date"]),
            models.Index(fields=["tenant", "branch", "date"]),
        ]


class ProductVelocity(TenantScopedModel):
    """One row per (tenant, product, branch, date). Source for item-wise,
    category, top/slow movers, branch comparison."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE)
    branch = models.ForeignKey("tenants.Branch", on_delete=models.CASCADE)
    date = models.DateField()
    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    # `revenue` is GROSS turnover = SUM(line_total) (tax-INCLUSIVE). `net_revenue`
    # is tax-EXCLUSIVE (line_total − tax − further_tax) and is what revenue/margin
    # reports must use — margin = net_revenue − cogs (both tax-exclusive).
    revenue = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    net_revenue = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cogs = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    last_built_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "branch", "date"],
                name="velocity_uniq_per_product_branch_day",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "date"]),
            models.Index(fields=["tenant", "product", "date"]),
        ]
