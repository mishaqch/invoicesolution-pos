"""TenantContextMiddleware — populates request.tenant for authenticated requests.

Runs after Django's AuthenticationMiddleware so request.user is set. Resolution:

  1. JWT carries `tenant_id` in its payload (set by PosTokenObtainPairSerializer).
     If present, use it after verifying an active membership exists.
  2. Otherwise, if the user has exactly one active TenantMembership, use that.
  3. Otherwise, X-Tenant-ID header (or `?tenant_id=` query) selects.
  4. If nothing matches, raise PermissionDenied (handled as 403).

Anonymous endpoints (auth, health, admin static) bypass entirely.
"""

from __future__ import annotations

from typing import Iterable

import json

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.tenants.models import TenantMembership


def _forbid(detail: str) -> JsonResponse:
    """Return a DRF-shaped 403 from middleware (matches `{detail: ...}`)."""
    return JsonResponse({"detail": detail}, status=403)

EXEMPT_PREFIXES: tuple[str, ...] = (
    "/admin/",
    "/api/health/",
    "/api/auth/login/",
    "/api/auth/refresh/",
    "/api/auth/pin-login/",
    "/static/",
    "/media/",
    # Local PRAL mock gateway (mounted only when DEBUG, see core/urls.py).
    # These carry a PRAL *bearer* (not our JWT); without exemption this
    # middleware would try to decode it as a JWT and 401. They 404 in prod.
    "/__mock_pral/",
    "/pdi/",
)

# Phase 0 platform stub. Endpoints under these prefixes are reachable
# ONLY by platform-staff users (is_platform_staff=true). Tenant API
# endpoints are everything else under /api/, and are blocked for
# platform staff unless mid-impersonation (Phase 9).
PLATFORM_PREFIXES: tuple[str, ...] = (
    "/api/platform/",
)

# Endpoints that are tenant-side BUT also legitimately reachable by
# platform staff and by users-without-a-membership. They report on
# WHO the caller is, not on tenant data. The React tenant admin calls
# /auth/me/ on shell mount to detect a broken session — if it 403s
# here we'd never see the broken-session signal and would loop on
# 403s forever. Logout / refresh also fall into this category.
PLATFORM_STAFF_ALLOWED_TENANT_PATHS: tuple[str, ...] = (
    "/api/auth/me/",
    "/api/auth/logout/",
)


def _is_exempt(path: str, prefixes: Iterable[str] = EXEMPT_PREFIXES) -> bool:
    return any(path.startswith(p) for p in prefixes)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._jwt_auth = JWTAuthentication()

    def __call__(self, request):
        request.tenant = None
        request.tenant_id = None

        if _is_exempt(request.path):
            return self.get_response(request)

        # The JWTAuthentication runs in DRF view dispatch, which is *after*
        # middleware. To access JWT claims here we run authentication early.
        #
        # When the token is EXPIRED (or otherwise invalid), we MUST surface
        # a 401 with the WWW-Authenticate header — not silently swallow.
        # Swallowing turns the request into "anonymous-but-tenant-scoped",
        # and downstream permission checks (HasModule, HasRolePerm) then
        # return 403 because there's no authenticated user. The client
        # only refreshes on 401, so the user gets stuck in a 403 loop
        # forever — exactly the "every-time-I-open-my-laptop" pattern.
        #
        # Other exceptions (DB errors, unrelated bugs) we still swallow
        # so middleware doesn't 500 a tenant-context resolution issue.
        token_payload = None
        try:
            auth = self._jwt_auth.authenticate(request)
            if auth is not None:
                user, validated_token = auth
                request.user = user
                token_payload = validated_token.payload
        except (InvalidToken, TokenError) as exc:
            # Token sent but expired/forged/malformed. Return 401 so the
            # admin-web client knows to try the refresh-token flow.
            resp = JsonResponse(
                {"detail": "Token is invalid or expired.",
                 "code": "token_not_valid"},
                status=401,
            )
            resp["WWW-Authenticate"] = 'Bearer realm="api"'
            return resp
        except Exception:
            # Unrelated infrastructure error — keep swallowing so we
            # don't 500 in middleware. View will reject as unauthenticated.
            pass

        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return self.get_response(request)

        # Phase 0 platform stub: platform-staff users are blocked from
        # tenant-scoped endpoints (everything under /api/ except /api/platform/
        # and the EXEMPT_PREFIXES). Conversely, non-platform users are blocked
        # from /api/platform/ endpoints. Phase 9 adds an impersonation context
        # that lets platform staff cross the boundary, audited.
        is_platform_request = any(
            request.path.startswith(p) for p in PLATFORM_PREFIXES
        )
        is_platform_user = bool(getattr(request.user, "is_platform_staff", False))
        is_identity_path = request.path in PLATFORM_STAFF_ALLOWED_TENANT_PATHS
        if is_platform_request and not is_platform_user:
            return _forbid("Platform staff only.")
        if (
            (not is_platform_request)
            and is_platform_user
            and request.path.startswith("/api/")
            and not is_identity_path
        ):
            return _forbid(
                "Platform staff cannot access tenant API endpoints directly. "
                "Use /api/platform/* or impersonate (Phase 9).",
            )

        tenant_id = self._resolve_tenant_id(request, token_payload)
        if tenant_id is None:
            return self.get_response(request)

        membership = (
            TenantMembership.objects
            .select_related("tenant")
            .filter(user=request.user, tenant_id=tenant_id, is_active=True)
            .first()
        )
        if membership is None:
            raise PermissionDenied("You are not an active member of this tenant.")

        request.tenant = membership.tenant
        request.tenant_id = membership.tenant_id
        request.tenant_membership = membership
        return self.get_response(request)

    @staticmethod
    def _resolve_tenant_id(request, token_payload):
        if token_payload and "tenant_id" in token_payload:
            return token_payload["tenant_id"]

        active = TenantMembership.objects.filter(user=request.user, is_active=True)
        if active.count() == 1:
            return str(active.first().tenant_id)

        header = request.headers.get("X-Tenant-ID") or request.GET.get("tenant_id")
        return header or None
