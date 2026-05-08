"""Celery app — defined here so `core/__init__.py` can import it lazily.

Phase 1 adds:
  - inventory.low_stock_digest @ 07:00 PKT daily.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# Schedule timezone follows Django's TIME_ZONE (Asia/Karachi by default).
app.conf.beat_schedule = {
    "low-stock-digest-daily": {
        "task": "inventory.low_stock_digest",
        "schedule": crontab(hour=7, minute=0),
    },
    # Phase 4 — FBR
    "fbr-finalize-aged-invoices-hourly": {
        "task": "fbr.finalize_aged_invoices",
        "schedule": crontab(minute=0),
    },
    "fbr-recompute-monthly-budgets": {
        "task": "fbr.recompute_monthly_budgets",
        # 00:05 PKT on the 1st of each month. Django's TIME_ZONE is PKT,
        # and Celery is configured to use that timezone too.
        "schedule": crontab(hour=0, minute=5, day_of_month=1),
    },
}


@app.task(bind=True)
def debug_task(self):  # type: ignore[no-untyped-def]
    print(f"Request: {self.request!r}")
