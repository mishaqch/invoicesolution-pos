"""Celery app — defined here so `core/__init__.py` can import it lazily.

Phase 0 ships the worker + beat services; no scheduled tasks yet. The first
real task lands in Phase 1 (low-stock digest).
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # type: ignore[no-untyped-def]
    print(f"Request: {self.request!r}")
