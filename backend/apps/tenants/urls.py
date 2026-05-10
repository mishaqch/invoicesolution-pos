from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BranchViewSet,
    OnboardingStateView,
    TenantModulesView,
    TerminalViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("terminals", TerminalViewSet, basename="terminal")

urlpatterns = [
    path("onboarding/", OnboardingStateView.as_view(), name="onboarding-state"),
    path("me/modules/", TenantModulesView.as_view(), name="me-modules"),
    *router.urls,
]
