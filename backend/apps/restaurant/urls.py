from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    FloorView,
    KdsView,
    ModifierGroupViewSet,
    OrderActionView,
    TableViewSet,
)

router = DefaultRouter()
router.register("tables", TableViewSet, basename="table")
router.register("modifier-groups", ModifierGroupViewSet, basename="modifier-group")

urlpatterns = [
    path("floor/", FloorView.as_view(), name="restaurant-floor"),
    path("kds/", KdsView.as_view(), name="restaurant-kds"),
    path("orders/<uuid:pk>/<str:op>/", OrderActionView.as_view(), name="restaurant-order-action"),
    *router.urls,
]
