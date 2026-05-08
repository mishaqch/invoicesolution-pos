from rest_framework.routers import DefaultRouter

from .views import (
    AdjustmentView,
    StockAuditViewSet,
    StockLevelViewSet,
    StockMovementViewSet,
    StockTransferViewSet,
)

router = DefaultRouter()
router.register("stock-levels", StockLevelViewSet, basename="stocklevel")
router.register("movements", StockMovementViewSet, basename="movement")
router.register("adjustments", AdjustmentView, basename="adjustment")
router.register("transfers", StockTransferViewSet, basename="transfer")
router.register("audits", StockAuditViewSet, basename="audit")

urlpatterns = router.urls
