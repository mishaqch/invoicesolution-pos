from rest_framework.routers import DefaultRouter

from .views import CustomerGroupViewSet, CustomerLedgerViewSet, CustomerViewSet

router = DefaultRouter()
router.register("groups", CustomerGroupViewSet, basename="customer-group")
router.register("ledger", CustomerLedgerViewSet, basename="customer-ledger")
router.register("", CustomerViewSet, basename="customer")

urlpatterns = router.urls
