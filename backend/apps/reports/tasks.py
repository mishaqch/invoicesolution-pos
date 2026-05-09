"""Celery tasks for reports.

- rebuild_aggregates_today: runs every 5 min during business hours,
  hourly otherwise. Refreshes today's row for every tenant.
- rebuild_aggregates_yesterday: 02:00 PKT — repaints yesterday so any
  late-arriving sync lands in the right day.
- run_async_report: queued from the API when a filter spans too many
  rows for a sync request. Generates the requested export and writes
  it to MEDIA_ROOT, then flips the ReportRun row to 'ready'.
"""

from __future__ import annotations

import datetime as dt
import logging
import traceback
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.tenants.models import Tenant

from .aggregates import rebuild_daily_sales, rebuild_product_velocity
from .models import ReportRun

log = logging.getLogger(__name__)


@shared_task(name="reports.rebuild_aggregates_today")
def rebuild_aggregates_today() -> dict:
    today = timezone.localdate()
    return _rebuild_for_date(today)


@shared_task(name="reports.rebuild_aggregates_yesterday")
def rebuild_aggregates_yesterday() -> dict:
    yesterday = timezone.localdate() - dt.timedelta(days=1)
    return _rebuild_for_date(yesterday)


def _rebuild_for_date(d: dt.date) -> dict:
    tenants_processed = 0
    daily_rows = 0
    velocity_rows = 0
    for tenant in Tenant.objects.all():
        try:
            daily_rows += rebuild_daily_sales(tenant, date_from=d, date_to=d)
            velocity_rows += rebuild_product_velocity(tenant, date_from=d, date_to=d)
            tenants_processed += 1
        except Exception:
            log.exception("aggregate rebuild failed for tenant %s on %s", tenant.id, d)
    return {
        "date": d.isoformat(),
        "tenants_processed": tenants_processed,
        "daily_rows": daily_rows,
        "velocity_rows": velocity_rows,
    }


@shared_task(name="reports.run_async_report")
def run_async_report(report_run_id: str) -> dict:
    """Generate the requested export for a ReportRun row.

    Imports inside the function avoid a module-load cycle (registry imports
    individual report modules which import models).
    """
    from .registry import get
    from .base import BaseFilters
    from .exports import excel_response, pdf_response, streaming_csv_response

    run = ReportRun.objects.select_related("tenant").get(pk=report_run_id)
    run.status = "running"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    try:
        report_cls = get(run.report_name)
        filters = report_cls.Filters(**run.filters_json)
        report = report_cls(tenant_id=str(run.tenant_id), filters=filters)
        result = report.run(use_cache=False, cap=1_000_000)

        out_dir = Path(settings.MEDIA_ROOT) / "reports" / str(run.tenant_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        ext = run.export_format or "csv"
        out_path = out_dir / f"{run.report_name}-{ts}.{ext}"

        # Write the file directly.
        if ext == "csv":
            with open(out_path, "wb") as f:
                resp = streaming_csv_response(result, filename=out_path.name)
                for chunk in resp.streaming_content:
                    f.write(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        elif ext == "xlsx":
            resp = excel_response(result, filename=out_path.name)
            with open(out_path, "wb") as f:
                f.write(resp.content)
        elif ext == "pdf":
            resp = pdf_response(
                result, filename=out_path.name,
                title=run.report_name.replace("_", " ").title(),
                tenant_business_name=run.tenant.business_name,
                tenant_ntn=run.tenant.ntn,
            )
            with open(out_path, "wb") as f:
                f.write(resp.content)
        else:
            raise ValueError(f"unsupported export_format {ext!r}")

        run.output_path = str(out_path.relative_to(settings.MEDIA_ROOT))
        run.row_count = result.row_count
        run.status = "ready"
        run.finished_at = timezone.now()
        run.save(update_fields=[
            "output_path", "row_count", "status", "finished_at",
        ])
        return {"id": str(run.id), "status": "ready", "path": run.output_path}
    except Exception as exc:
        run.status = "failed"
        run.error = f"{exc}\n{traceback.format_exc()}"[:4000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        log.exception("async report failed: %s", run.id)
        raise
