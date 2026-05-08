from django.urls import path

from .views import LoginView, LogoutView, MeView, PinLoginView, RefreshView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth_login"),
    path("pin-login/", PinLoginView.as_view(), name="auth_pin_login"),
    path("refresh/", RefreshView.as_view(), name="auth_refresh"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("me/", MeView.as_view(), name="auth_me"),
]
