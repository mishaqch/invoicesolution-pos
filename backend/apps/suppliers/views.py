"""Supplier API. Tenant-scoped; gated on the inventory module + owner/manager."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import filters, viewsets

from apps.accounts.permissions import HasModule, HasRolePerm

from .models import Supplier
from .serializers import SupplierSerializer

_INVENTORY_GATE = HasModule.for_module("inventory")


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.filter(deleted_at__isnull=True)
    serializer_class = SupplierSerializer
    permission_classes = [_INVENTORY_GATE, HasRolePerm.with_perm("inventory.adjust")]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "contact_person", "phone", "ntn"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        # Audit, don't delete.
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])
