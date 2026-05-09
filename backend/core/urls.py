"""Top-level URL conf."""

from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


def readyz(_request):
    """Distinct from healthcheck: also verifies DB + Redis are reachable.

    Used by load balancers / k8s readiness probes. Returns 503 when any
    dependency is down so the orchestrator stops routing to the instance.
    """
    checks = {"db": False, "cache": False}
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            checks["db"] = cur.fetchone() == (1,)
    except Exception as exc:
        checks["db_error"] = str(exc)[:200]
    try:
        cache.set("readyz_probe", "1", 5)
        checks["cache"] = cache.get("readyz_probe") == "1"
    except Exception as exc:
        checks["cache_error"] = str(exc)[:200]

    ok = checks["db"] and checks["cache"]
    return JsonResponse(
        {"status": "ok" if ok else "degraded", **checks},
        status=200 if ok else 503,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", healthcheck, name="health"),
    path("api/health/ready/", readyz, name="readyz"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.tenants.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/sync/", include("apps.sync.urls")),
    path("api/fbr/", include("apps.fbr.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/returns/", include("apps.returns.urls")),
    path("api/reports/", include("apps.reports.urls")),
]
