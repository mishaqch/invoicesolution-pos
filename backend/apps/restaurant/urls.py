from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    FloorView,
    KdsView,
    ModifierGroupViewSet,
    OpenOrderView,
    OrderActionView,
    ProductModifierGroupsView,
    TableViewSet,
)

router = DefaultRouter()
router.register("tables", TableViewSet, basename="table")
router.register("modifier-groups", ModifierGroupViewSet, basename="modifier-group")

urlpatterns = [
    path("floor/", FloorView.as_view(), name="restaurant-floor"),
    path("kds/", KdsView.as_view(), name="restaurant-kds"),
    # Open-order book: list/create/update + per-order resume (must precede the
    # <pk>/<op>/ action route so "orders/" isn't shadowed).
    path("orders/", OpenOrderView.as_view(), name="restaurant-open-orders"),
    path("orders/<uuid:pk>/<str:op>/", OrderActionView.as_view(), name="restaurant-order-action"),
    path("products/<uuid:product_id>/modifier-groups/", ProductModifierGroupsView.as_view(), name="restaurant-product-modifiers"),
    *router.urls,
]
