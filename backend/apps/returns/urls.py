from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import FindOriginalInvoiceView, ReturnViewSet

router = DefaultRouter()
router.register("", ReturnViewSet, basename="return")

urlpatterns = [
    path("find-invoice/", FindOriginalInvoiceView.as_view(), name="find-invoice"),
] + router.urls
