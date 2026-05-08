from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ActivateProductionTokenView,
    CancelBudgetView,
    CancelInvoiceFbrView,
    FbrIpWhitelistViewSet,
    FbrStatusView,
    ScenarioTestViewSet,
    SubmissionViewSet,
    SubmitSandboxTokenView,
)

router = DefaultRouter()
router.register("scenarios", ScenarioTestViewSet, basename="fbr-scenario")
router.register("submissions", SubmissionViewSet, basename="fbr-submission")
router.register("ip-whitelist", FbrIpWhitelistViewSet, basename="fbr-ip")

urlpatterns = [
    path("status/", FbrStatusView.as_view(), name="fbr-status"),
    path("tokens/sandbox/", SubmitSandboxTokenView.as_view(), name="fbr-sandbox-token"),
    path("tokens/production/", ActivateProductionTokenView.as_view(), name="fbr-prod-token"),
    path("cancel-budget/", CancelBudgetView.as_view(), name="fbr-cancel-budget"),
    path("invoices/<uuid:invoice_id>/cancel/",
         CancelInvoiceFbrView.as_view(), name="fbr-invoice-cancel"),
] + router.urls
