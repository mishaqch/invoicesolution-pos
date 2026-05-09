from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BranchViewSet, OnboardingStateView, TerminalViewSet

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("terminals", TerminalViewSet, basename="terminal")

urlpatterns = [
    path("onboarding/", OnboardingStateView.as_view(), name="onboarding-state"),
    *router.urls,
]
