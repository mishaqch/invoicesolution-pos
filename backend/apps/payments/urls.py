from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ChequeViewSet,
    PaymentMethodsView,
    PaymentSettingsView,
)

router = DefaultRouter()
router.register("cheques", ChequeViewSet, basename="cheque")

urlpatterns = [
    path("methods/", PaymentMethodsView.as_view(), name="payment-methods"),
    path("settings/", PaymentSettingsView.as_view(), name="payment-settings"),
] + router.urls
