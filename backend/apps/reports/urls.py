from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ReportExportView,
    ReportFavoriteViewSet,
    ReportPreviewView,
    ReportRegistryView,
    ReportRunViewSet,
    dashboard_view,
)


router = DefaultRouter()
router.register(r"runs", ReportRunViewSet, basename="report-run")
router.register(r"favorites", ReportFavoriteViewSet, basename="report-favorite")


urlpatterns = [
    path("", ReportRegistryView.as_view(), name="reports-registry"),
    path("dashboard/", dashboard_view, name="reports-dashboard"),
    path("<str:name>/preview/", ReportPreviewView.as_view(), name="report-preview"),
    path("<str:name>/export/", ReportExportView.as_view(), name="report-export"),
    path("", include(router.urls)),
]
