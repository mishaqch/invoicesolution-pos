from django.urls import path
from rest_framework.routers import DefaultRouter

# Staff (cashier / user) management. Lives in apps.accounts but is mounted here
# under /api/users/ alongside branches/terminals — it's the same admin surface.
from apps.accounts.user_management_views import MembershipViewSet

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
router.register("users", MembershipViewSet, basename="user-management")

urlpatterns = [
    path("onboarding/", OnboardingStateView.as_view(), name="onboarding-state"),
    path("me/modules/", TenantModulesView.as_view(), name="me-modules"),
    path("tenants/me/setup/", TenantSetupView.as_view(), name="tenant-setup"),
    *router.urls,
]
