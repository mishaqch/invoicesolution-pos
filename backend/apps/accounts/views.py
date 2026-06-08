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
    SupervisorPinVerifySerializer,
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


class SupervisorPinVerifyView(APIView):
    """Verify a manager/owner PIN to authorize a till action (void/edit/
    discount). Requires the CASHIER to be authenticated (so we know the tenant
    + who requested it), verifies the supervisor PIN server-side, audit-logs the
    authorization, and returns the supervisor's role — but NO token.

    Body: { email, pin, action, context? }  (action/context for the audit trail)
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"  # share the strict auth throttle (anti-bruteforce)

    def post(self, request):
        tenant_id = getattr(request, "tenant_id", None)
        ser = SupervisorPinVerifySerializer(
            data=request.data, context={"tenant_id": tenant_id},
        )
        ser.is_valid(raise_exception=True)
        supervisor = ser.validated_data["user"]
        role = ser.validated_data["role"]

        from apps.audit.services import log as audit_log
        action = (request.data.get("action") or "till_action")[:50]
        audit_log(
            tenant_id=tenant_id,
            user=supervisor,
            entity_type="approval",
            action=f"supervisor_authorized:{action}",
            after={
                "authorized_by": supervisor.email,
                "role": role,
                "requested_by": getattr(request.user, "email", None),
                "context": (request.data.get("context") or {}),
            },
            request=request,
        )
        return Response({
            "valid": True,
            "role": role,
            "supervisor_name": supervisor.full_name,
            "supervisor_email": supervisor.email,
        })


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
