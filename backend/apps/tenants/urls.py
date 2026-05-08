from rest_framework.routers import DefaultRouter

from .views import BranchViewSet, TerminalViewSet

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("terminals", TerminalViewSet, basename="terminal")

urlpatterns = router.urls
