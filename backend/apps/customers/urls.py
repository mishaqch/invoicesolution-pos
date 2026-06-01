from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerGroupViewSet,
    CustomerImportView,
    CustomerLedgerViewSet,
    CustomerViewSet,
)

router = DefaultRouter()
router.register("groups", CustomerGroupViewSet, basename="customer-group")
router.register("ledger", CustomerLedgerViewSet, basename="customer-ledger")
router.register("", CustomerViewSet, basename="customer")

# `import/` is mounted BEFORE the customer router's catch-all detail
# route so it doesn't get treated as a customer pk.
urlpatterns = [
    path("import/", CustomerImportView.as_view(), name="customer-import"),
    *router.urls,
]
