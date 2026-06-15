from rest_framework.routers import DefaultRouter

from .views import (
    CatalogSyncView,
    CategoryViewSet,
    HsCodeViewSet,
    ProductBatchViewSet,
    ProductVariantViewSet,
    ProductViewSet,
    SaleTypeViewSet,
    TaxRateViewSet,
    UnitOfMeasureViewSet,
)

router = DefaultRouter()
router.register("uoms", UnitOfMeasureViewSet, basename="uom")
router.register("sale-types", SaleTypeViewSet, basename="saletype")
router.register("hs-codes", HsCodeViewSet, basename="hscode")
router.register("tax-rates", TaxRateViewSet, basename="taxrate")
router.register("categories", CategoryViewSet, basename="category")
router.register("variants", ProductVariantViewSet, basename="variant")
router.register("batches", ProductBatchViewSet, basename="batch")
router.register("products", ProductViewSet, basename="product")
router.register("sync", CatalogSyncView, basename="catalog-sync")

urlpatterns = router.urls
