"""Goods-receipt (GRN) API. Tenant-scoped; inventory module + owner/manager."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.response import Response

from apps.accounts.permissions import HasModule, HasRolePerm

from .models import GoodsReceipt
from .serializers import GoodsReceiptSerializer
from .services import post_receipt

_INVENTORY_GATE = HasModule.for_module("inventory")


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.select_related("supplier", "branch").prefetch_related("items")
    serializer_class = GoodsReceiptSerializer
    permission_classes = [_INVENTORY_GATE, HasRolePerm.with_perm("inventory.adjust")]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        qs = qs.filter(tenant_id=tenant_id)
        if (supplier := self.request.query_params.get("supplier")):
            qs = qs.filter(supplier_id=supplier)
        if (st := self.request.query_params.get("status")):
            qs = qs.filter(status=st)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id, created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="post")
    def post_grn(self, request, pk=None):
        """Post a draft GRN — creates batches + records purchase stock movements."""
        receipt = self.get_object()
        try:
            post_receipt(receipt, user=request.user)
        except DjValidationError as exc:
            raise DrfValidationError({"detail": exc.messages})
        return Response(
            GoodsReceiptSerializer(receipt).data, status=status.HTTP_200_OK,
        )
