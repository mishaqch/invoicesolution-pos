"""FBR submission report — every PRAL roundtrip with status, latency, retries."""

from __future__ import annotations

from dataclasses import dataclass

from apps.fbr.models import FbrSubmission

from ..base import BaseFilters, Column, Report
from ..registry import register


@dataclass
class _Filters(BaseFilters):
    only_failed: bool = False
    environment: str | None = None


@register
class FbrSubmissionsReport(Report):
    name = "fbr_submissions"
    Filters = _Filters
    columns = (
        Column("submitted_at", "Submitted", "datetime"),
        Column("environment", "Env"),
        Column("endpoint", "Endpoint"),
        Column("invoice_number", "Local invoice"),
        Column("fbr_invoice_number", "FBR invoice"),
        Column("status_code", "Code"),
        Column("http_status", "HTTP", "int", "right"),
        Column("attempt_number", "Attempt", "int", "right"),
        Column("duration_ms", "Latency ms", "int", "right"),
        Column("error_message", "Error"),
    )

    def query(self):
        qs = (
            FbrSubmission.objects.for_tenant(self.tenant_id)
            .select_related("invoice")
        )
        if self.filters.only_failed:
            qs = qs.exclude(status_code="00")
        if self.filters.environment:
            qs = qs.filter(environment=self.filters.environment)
        if self.filters.date_from:
            qs = qs.filter(submitted_at__date__gte=self.filters.date_from)
        if self.filters.date_to:
            qs = qs.filter(submitted_at__date__lte=self.filters.date_to)
        for s in qs.order_by("-submitted_at"):
            yield {
                "submitted_at": s.submitted_at,
                "environment": s.environment,
                "endpoint": s.endpoint,
                "invoice_number": s.invoice.local_invoice_number if s.invoice else "",
                "fbr_invoice_number": s.fbr_invoice_number or "",
                "status_code": s.status_code or "",
                "http_status": s.http_status,
                "attempt_number": s.attempt_number,
                "duration_ms": s.duration_ms,
                "error_message": (s.error_message or "")[:120],
            }
