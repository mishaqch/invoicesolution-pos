from rest_framework.routers import DefaultRouter

from .views import FolioViewSet, RoomViewSet

router = DefaultRouter()
router.register("rooms", RoomViewSet, basename="room")
router.register("folios", FolioViewSet, basename="folio")

urlpatterns = router.urls
