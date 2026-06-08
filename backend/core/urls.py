"""Top-level URL conf."""

from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
from django.urls import include, path


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


# Filename of the Windows terminal installer hosted for clients. Lives under
# MEDIA_ROOT/downloads/. In production nginx serves /downloads/ directly for
# speed; this Django view is the dev/fallback path and the canonical link
# admin-web points at.
TERMINAL_EXE_NAME = "invoiceSolution.exe"


def download_terminal_app(_request):
    """Serve the Electron POS terminal installer (invoiceSolution.exe).

    Public on purpose: the installer carries no secrets — a fresh terminal is
    useless until an owner-issued pairing code binds it to a branch. Hosting it
    unauthenticated lets a shopkeeper download it on the counter PC without
    first logging into admin-web there.
    """
    exe_path = Path(settings.MEDIA_ROOT) / "downloads" / TERMINAL_EXE_NAME
    if not exe_path.exists():
        raise Http404("Terminal installer not available yet.")
    return FileResponse(
        open(exe_path, "rb"),
        as_attachment=True,
        filename=TERMINAL_EXE_NAME,
        content_type="application/octet-stream",
    )


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
    path("api/suppliers/", include("apps.suppliers.urls")),
    path("api/purchases/", include("apps.purchases.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/sync/", include("apps.sync.urls")),
    path("api/fbr/", include("apps.fbr.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/returns/", include("apps.returns.urls")),
    path("api/reports/", include("apps.reports.urls")),
    # Public download for the Windows POS terminal installer. Linked from
    # admin-web (Terminals page → "Download Terminal App").
    path("download/terminal/", download_terminal_app, name="download_terminal_app"),
]

# Public share-link endpoint — NO auth, NO /api prefix. The route's
# HMAC-signed token IS the security boundary. Used by SendToBuyer to
# generate a wa.me / mailto URL the seller can paste into a message.
# See apps/sales/services/share_links.py for the trust model.
from apps.sales.views import public_invoice_pdf  # noqa: E402
urlpatterns += [
    # The `<str:token>` captures the .pdf suffix too so browsers auto-name
    # the download correctly. The view strips the suffix before unsigning.
    path("p/inv/<str:token>", public_invoice_pdf, name="public_invoice_pdf"),
]


# Local mock of the PRAL Digital Invoicing gateway. Enabled only when
# DEBUG=True so it can never be exposed in production. See
# apps/fbr/mock_pral.py for the contract and why this exists.
if settings.DEBUG:
    from apps.fbr import mock_pral

    _MOCK_BASE = "__mock_pral/di_data/v1/di/"
    urlpatterns += [
        path(f"{_MOCK_BASE}postinvoicedata_sb", mock_pral.post_invoice),
        path(f"{_MOCK_BASE}postinvoicedata", mock_pral.post_invoice),
        path(f"{_MOCK_BASE}validateinvoicedata_sb", mock_pral.validate_invoice),
        path(f"{_MOCK_BASE}validateinvoicedata", mock_pral.validate_invoice),
        path(f"{_MOCK_BASE}cancelinvoice_sb", mock_pral.cancel_invoice),
        path(f"{_MOCK_BASE}cancelinvoice", mock_pral.cancel_invoice),
        path(f"{_MOCK_BASE}editinvoice_sb", mock_pral.edit_invoice),
        path(f"{_MOCK_BASE}editinvoice", mock_pral.edit_invoice),
        # Reference endpoint the "Test connection" button probes. It lives at
        # /pdi/v1/uom (NOT under di_data). _normalise_pral_base() strips any
        # path from the configured endpoint, so a token pointed at
        # "http://localhost:8000/__mock_pral" probes "http://localhost:8000/
        # pdi/v1/uom" → mount at root. Also mount under __mock_pral for callers
        # that keep the full path.
        path("pdi/v1/uom", mock_pral.uom),
        path("__mock_pral/pdi/v1/uom", mock_pral.uom),
    ]
