"""Auth views: login (email+password), pin-login (cashier), refresh, logout, me."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.tenants.models import TenantMembership

from .serializers import (
    PinLoginSerializer,
    PosTokenObtainPairSerializer,
    TenantBriefSerializer,
    UserBriefSerializer,
)


class LoginView(TokenObtainPairView):
    """Email + password → access + refresh + tenant + role."""

    serializer_class = PosTokenObtainPairSerializer
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class PinLoginView(APIView):
    """Cashier PIN login (online in Phase 0)."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PinLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.to_representation(serializer.validated_data))


class LogoutView(APIView):
    """Blacklist the supplied refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "refresh token required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh).blacklist()
        except (TokenError, InvalidToken) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Current user + tenant + role."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = (
            TenantMembership.objects
            .select_related("tenant")
            .filter(user=request.user, is_active=True)
            .order_by("created_at")
            .first()
        )
        return Response({
            "user": UserBriefSerializer(request.user).data,
            "tenant": TenantBriefSerializer(membership.tenant).data if membership else None,
            "role": membership.role if membership else None,
        })
