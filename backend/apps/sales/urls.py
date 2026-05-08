from rest_framework.routers import DefaultRouter

from .views import CashSessionViewSet, InvoiceViewSet

router = DefaultRouter()
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("cash-sessions", CashSessionViewSet, basename="cashsession")

urlpatterns = router.urls
