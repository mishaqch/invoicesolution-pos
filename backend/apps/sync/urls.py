from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    IngestCustomerView,
    IngestInvoiceView,
    SyncLogViewSet,
    SyncStatusView,
)

router = DefaultRouter()
router.register("log", SyncLogViewSet, basename="sync-log")

urlpatterns = [
    path("invoices/", IngestInvoiceView.as_view(), name="sync-invoices"),
    path("customers/", IngestCustomerView.as_view(), name="sync-customers"),
    path("status/", SyncStatusView.as_view(), name="sync-status"),
] + router.urls
