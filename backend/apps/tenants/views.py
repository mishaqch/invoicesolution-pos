"""ViewSets for branches + terminals."""

from __future__ import annotations

from rest_framework import viewsets

from apps.accounts.permissions import HasRolePerm

from .models import Branch, Terminal
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
