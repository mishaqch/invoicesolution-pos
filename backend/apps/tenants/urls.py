from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BranchViewSet,
    OnboardingStateView,
    TenantModulesView,
    TenantSetupView,
    TerminalViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("terminals", TerminalViewSet, basename="terminal")

urlpatterns = [
    path("onboarding/", OnboardingStateView.as_view(), name="onboarding-state"),
    path("me/modules/", TenantModulesView.as_view(), name="me-modules"),
    path("tenants/me/setup/", TenantSetupView.as_view(), name="tenant-setup"),
    *router.urls,
]
