from rest_framework.routers import DefaultRouter

from .views import (
    AdjustmentView,
    ExpiryViewSet,
    RestockViewSet,
    StockAuditViewSet,
    StockLevelViewSet,
    StockMovementViewSet,
    StockTransferViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("stock-levels", StockLevelViewSet, basename="stocklevel")
router.register("restock", RestockViewSet, basename="restock")
router.register("expiry", ExpiryViewSet, basename="expiry")
router.register("movements", StockMovementViewSet, basename="movement")
router.register("adjustments", AdjustmentView, basename="adjustment")
router.register("transfers", StockTransferViewSet, basename="transfer")
router.register("audits", StockAuditViewSet, basename="audit")

urlpatterns = router.urls
