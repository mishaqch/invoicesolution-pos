"""ViewSets for branches + terminals; onboarding-state endpoint."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasRolePerm
from apps.sales.models import Invoice

from .models import Branch, Tenant, Terminal
from .serializers import BranchSerializer, TerminalSerializer


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class BranchViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.filter(deleted_at__isnull=True).order_by("name")
    serializer_class = BranchSerializer
    permission_classes = [HasRolePerm.with_perm("settings.business_profile")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class TerminalViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Terminal.objects.select_related("branch").order_by("branch__name", "name")
    serializer_class = TerminalSerializer
    permission_classes = [HasRolePerm.with_perm("settings.business_profile")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class OnboardingStateView(APIView):
    """GET / PATCH the tenant's onboarding wizard progress.

    Also returns derived flags so the admin web can decide whether to
    show the wizard at all without a second roundtrip:

      - has_branch     — at least one Branch row
      - has_terminal   — at least one Terminal row
      - has_product    — at least one Product (Phase 1) — checked lazily
                         to avoid a circular import at module load time
      - has_first_sale — at least one Invoice (any status)
    """

    permission_classes = [IsAuthenticated]

    def _tenant(self, request) -> Tenant:
        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            raise PermissionDenied("Tenant context required.")
        return Tenant.objects.get(pk=tenant_id)

    def get(self, request):
        from apps.catalog.models import Product
        tenant = self._tenant(request)
        return Response({
            "state": tenant.onboarding_state or {},
            "derived": {
                "has_branch": Branch.objects.filter(
                    tenant=tenant, deleted_at__isnull=True,
                ).exists(),
                "has_terminal": Terminal.objects.filter(tenant=tenant).exists(),
                "has_product": Product.objects.filter(
                    tenant=tenant, deleted_at__isnull=True,
                ).exists(),
                "has_first_sale": Invoice.objects.for_tenant(tenant.id).exists(),
            },
        })

    def patch(self, request):
        tenant = self._tenant(request)
        new_keys = request.data or {}
        if not isinstance(new_keys, dict):
            return Response({"detail": "Body must be a JSON object."}, status=400)
        merged = {**(tenant.onboarding_state or {}), **new_keys}
        tenant.onboarding_state = merged
        tenant.save(update_fields=["onboarding_state", "updated_at"])
        return Response({"state": merged})
