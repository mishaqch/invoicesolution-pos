"""Top-level URL conf."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", healthcheck, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.tenants.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/sync/", include("apps.sync.urls")),
    path("api/fbr/", include("apps.fbr.urls")),
]
