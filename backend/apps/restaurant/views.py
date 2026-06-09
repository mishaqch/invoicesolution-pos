"""Restaurant API — gated on the `restaurant` module + owner/manager perms.

Tables + modifier catalog are CRUD ViewSets. Kitchen/floor are read+action
endpoints over held sales.Invoices (orders are invoices, not a separate model).
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasModule, HasRolePerm, IsTenantMember
from apps.sales.models import Invoice

from . import services
from .models import Modifier, ModifierGroup, Table
from .serializers import (
    ModifierGroupSerializer,
    ModifierGroupWriteSerializer,
    TableSerializer,
)

_RESTAURANT_GATE = HasModule.for_module("restaurant")


class _TenantScoped:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class TableViewSet(_TenantScoped, viewsets.ModelViewSet):
    queryset = Table.objects.filter(deleted_at__isnull=True).select_related("branch")
    serializer_class = TableSerializer
    permission_classes = [_RESTAURANT_GATE, HasRolePerm.with_perm("settings.business_profile")]

    def get_queryset(self):
        qs = super().get_queryset()
        if (branch := self.request.query_params.get("branch")):
            qs = qs.filter(branch_id=branch)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


class ModifierGroupViewSet(_TenantScoped, viewsets.ModelViewSet):
    queryset = (
        ModifierGroup.objects.filter(deleted_at__isnull=True)
        .prefetch_related("modifiers")
    )
    permission_classes = [_RESTAURANT_GATE, HasRolePerm.with_perm("products.manage")]

    def get_serializer_class(self):
        return ModifierGroupSerializer if self.action in ("list", "retrieve") else ModifierGroupWriteSerializer

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


def _order_payload(inv: Invoice) -> dict:
    """Compact order shape for the floor + KDS views."""
    return {
        "id": str(inv.id),
        "local_invoice_number": inv.local_invoice_number,
        "order_type": inv.order_type,
        "order_status": inv.order_status,
        "table": inv.table.name if inv.table_id else None,
        "table_id": str(inv.table_id) if inv.table_id else None,
        "covers": inv.covers,
        "kitchen_sent_at": inv.kitchen_sent_at.isoformat() if inv.kitchen_sent_at else None,
        "grand_total": str(inv.grand_total),
        "items": [
            {
                "name": it.product_name,
                "quantity": str(it.quantity),
                "modifiers": it.modifiers or [],
                "item_note": it.item_note,
                "course": it.course,
                "sent_to_kitchen": it.sent_to_kitchen,
                "is_cancelled": it.is_cancelled,
            }
            for it in inv.items.all()
        ],
    }


class FloorView(APIView):
    """GET /api/restaurant/floor/ — tables + their open order (if any)."""
    permission_classes = [_RESTAURANT_GATE, IsTenantMember]

    def get(self, request):
        tenant_id = request.tenant_id
        branch_id = request.query_params.get("branch")
        tables = Table.objects.filter(
            tenant_id=tenant_id, deleted_at__isnull=True, is_active=True,
        )
        if branch_id:
            tables = tables.filter(branch_id=branch_id)
        orders = {
            o.table_id: o
            for o in services.open_orders_qs(tenant_id, branch_id=branch_id)
            if o.table_id
        }
        return Response({
            "tables": [
                {
                    "id": str(t.id), "name": t.name, "seats": t.seats, "zone": t.zone,
                    "order": _order_payload(orders[t.id]) if t.id in orders else None,
                }
                for t in tables.order_by("display_order", "name")
            ],
        })


class KdsView(APIView):
    """GET /api/restaurant/kds/ — kitchen queue (fired, not-yet-served orders)."""
    permission_classes = [_RESTAURANT_GATE, IsTenantMember]

    def get(self, request):
        branch_id = request.query_params.get("branch")
        orders = services.open_orders_qs(request.tenant_id, branch_id=branch_id).filter(
            order_status__in=["sent_to_kitchen", "ready"],
        )
        return Response({"orders": [_order_payload(o) for o in orders]})


class OrderActionView(APIView):
    """POST /api/restaurant/orders/<id>/<send-to-kitchen|ready|served>/."""
    permission_classes = [_RESTAURANT_GATE, IsTenantMember]

    def post(self, request, pk, op):
        try:
            invoice = Invoice.objects.for_tenant(request.tenant_id).get(pk=pk)
        except Invoice.DoesNotExist:
            raise NotFound("Order not found.")
        if op == "send-to-kitchen":
            services.send_to_kitchen(invoice, user=request.user, request=request)
        elif op in ("ready", "served"):
            services.set_order_status(invoice, op, user=request.user, request=request)
        else:
            raise ValidationError({"op": "Unknown action."})
        return Response(_order_payload(invoice), status=status.HTTP_200_OK)
