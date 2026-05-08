"""Inventory API."""

from __future__ import annotations

from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import HasRolePerm, IsTenantMember
from apps.catalog.models import Product, ProductVariant
from apps.tenants.models import Branch

from .models import (
    StockAudit,
    StockAuditItem,
    StockLevel,
    StockMovement,
    StockTransfer,
    StockTransferItem,
)
from .serializers import (
    AdjustmentSerializer,
    StockAuditItemSerializer,
    StockAuditSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    StockTransferItemSerializer,
    StockTransferSerializer,
)
from .services import audits as audit_svc
from .services import transfers as transfer_svc
from .services.movements import record_movement


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Stock levels — read-only list
# ---------------------------------------------------------------------------


class StockLevelViewSet(_TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = StockLevel.objects.select_related("product", "branch", "variant").all()
    serializer_class = StockLevelSerializer
    permission_classes = [IsTenantMember]
    filter_backends = [filters.OrderingFilter]
    ordering = ["product__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (low := params.get("low_stock")) and low.lower() in ("1", "true"):
            from django.db.models import F, Value
            from django.db.models.functions import Coalesce
            qs = qs.filter(quantity__lte=Coalesce(F("reorder_level"), Value(0)))
        return qs


# ---------------------------------------------------------------------------
# Stock movements — read-only ledger
# ---------------------------------------------------------------------------


class StockMovementViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = StockMovement.objects.select_related("product", "branch").order_by("-created_at")
    serializer_class = StockMovementSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (p := params.get("product")):
            qs = qs.filter(product_id=p)
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (mt := params.get("movement_type")):
            qs = qs.filter(movement_type=mt)
        if (start := params.get("from")):
            qs = qs.filter(created_at__gte=start)
        if (end := params.get("to")):
            qs = qs.filter(created_at__lte=end)
        return qs


# ---------------------------------------------------------------------------
# Adjustments (POST-only)
# ---------------------------------------------------------------------------


class AdjustmentView(viewsets.ViewSet):
    permission_classes = [HasRolePerm.with_perm("inventory.adjust")]

    def create(self, request):
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        try:
            branch = Branch.objects.for_tenant(request.tenant_id).get(pk=v["branch"])
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")

        try:
            product = Product.objects.for_tenant(request.tenant_id).get(pk=v["product"])
        except Product.DoesNotExist:
            raise NotFound("Product not found.")

        variant = None
        if v.get("variant"):
            try:
                variant = ProductVariant.objects.get(
                    pk=v["variant"], product__tenant_id=request.tenant_id
                )
            except ProductVariant.DoesNotExist:
                raise NotFound("Variant not found.")

        # Sign convention: explicit adjustment_in/adjustment_out from caller.
        # Quantity is always recorded as a signed delta.
        signed_qty = v["quantity"]
        if v["movement_type"] in ("adjustment_out", "damage", "expiry") and signed_qty > 0:
            signed_qty = -signed_qty

        movement = record_movement(
            tenant_id=request.tenant_id,
            product=product,
            variant=variant,
            branch=branch,
            movement_type=v["movement_type"],
            quantity=signed_qty,
            reason=v["reason"],
            performed_by=request.user,
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Stock transfers
# ---------------------------------------------------------------------------


class StockTransferViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = (
        StockTransfer.objects.select_related("from_branch", "to_branch")
        .prefetch_related("items").order_by("-created_at")
    )
    serializer_class = StockTransferSerializer
    permission_classes = [HasRolePerm.with_perm("inventory.adjust")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    @action(detail=True, methods=["post"], url_path="add-item")
    def add_item(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != "draft":
            raise ValidationError({"status": "Cannot add items after dispatch."})
        item_ser = StockTransferItemSerializer(data={**request.data, "transfer": str(transfer.id)})
        item_ser.is_valid(raise_exception=True)
        item_ser.save()
        return Response(item_ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def dispatch(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer_svc.dispatch(transfer, dispatched_by=request.user)
        except Exception as e:  # ValidationError or other
            raise ValidationError(getattr(e, "message_dict", {"detail": str(e)}))
        return Response(self.get_serializer(transfer).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        transfer = self.get_object()
        counts = request.data.get("counts", [])
        try:
            transfer_svc.receive(
                transfer,
                [(c["item"], c["quantity_received"]) for c in counts],
                received_by=request.user,
            )
        except Exception as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": str(e)}))
        return Response(self.get_serializer(transfer).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer_svc.cancel(transfer)
        except Exception as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": str(e)}))
        return Response(self.get_serializer(transfer).data)


# ---------------------------------------------------------------------------
# Stock audits
# ---------------------------------------------------------------------------


class StockAuditViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = (
        StockAudit.objects.select_related("branch")
        .prefetch_related("items").order_by("-started_at")
    )
    serializer_class = StockAuditSerializer
    permission_classes = [HasRolePerm.with_perm("inventory.adjust")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    @action(detail=True, methods=["post"], url_path="add-item")
    def add_item(self, request, pk=None):
        audit = self.get_object()
        if audit.status != "in_progress":
            raise ValidationError({"status": "Cannot add items after finalize."})
        item_ser = StockAuditItemSerializer(data={**request.data, "audit": str(audit.id)})
        item_ser.is_valid(raise_exception=True)
        item_ser.save()
        return Response(item_ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        audit = self.get_object()
        try:
            audit_svc.finalize(audit, performed_by=request.user)
        except Exception as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": str(e)}))
        return Response(self.get_serializer(audit).data)
