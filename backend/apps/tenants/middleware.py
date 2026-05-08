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

from django.core.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.tenants.models import TenantMembership

EXEMPT_PREFIXES: tuple[str, ...] = (
    "/admin/",
    "/api/health/",
    "/api/auth/login/",
    "/api/auth/refresh/",
    "/api/auth/pin-login/",
    "/static/",
    "/media/",
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
        # Catch failures silently — the view's permission_classes will reject.
        token_payload = None
        try:
            auth = self._jwt_auth.authenticate(request)
            if auth is not None:
                user, validated_token = auth
                request.user = user
                token_payload = validated_token.payload
        except Exception:
            pass

        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return self.get_response(request)

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
