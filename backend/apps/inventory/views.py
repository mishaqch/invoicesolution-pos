"""Inventory API."""

from __future__ import annotations

from django.db import transaction
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    HasAnyModule,
    HasModule,
    HasRolePerm,
    IsTenantMember,
)

# Most endpoints in this module gate on the "inventory" module (POS tenants).
_INVENTORY_GATE = HasModule.for_module("inventory")
# Endpoints shared with Digital-Invoicing warehouse tenants accept either the
# POS `inventory` module OR the DI `warehouses` module.
_STOCK_GATE = HasAnyModule.for_modules("inventory", "warehouses")
# Warehouse CRUD is DI-only.
_WAREHOUSE_GATE = HasModule.for_module("warehouses")
from apps.catalog.models import Product, ProductBatch, ProductVariant
from apps.tenants.models import Branch

from .models import (
    StockAudit,
    StockAuditItem,
    StockLevel,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    Warehouse,
)
from .serializers import (
    AdjustmentSerializer,
    StockAuditItemSerializer,
    StockAuditSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    StockTransferItemSerializer,
    StockTransferSerializer,
    WarehouseSerializer,
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


class StockLevelViewSet(
    _TenantQuerySetMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = StockLevel.objects.select_related(
        "product", "branch", "variant", "warehouse",
    ).all()
    serializer_class = StockLevelSerializer
    permission_classes = [_STOCK_GATE, IsTenantMember]
    filter_backends = [filters.OrderingFilter]
    ordering = ["product__name"]

    def get_permissions(self):
        # Deleting a stock row is a mutation — require the adjust perm (list
        # stays open to any tenant member).
        if self.action == "destroy":
            return [_STOCK_GATE(), HasRolePerm.with_perm("inventory.adjust")()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (p := params.get("product")):
            qs = qs.filter(product_id=p)
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (w := params.get("warehouse")):
            qs = qs.filter(warehouse_id=w)
        if (low := params.get("low_stock")) and low.lower() in ("1", "true"):
            from django.db.models import F, Value
            from django.db.models.functions import Coalesce
            qs = qs.filter(quantity__lte=Coalesce(F("reorder_level"), Value(0)))
        return qs

    def perform_destroy(self, instance):
        # Remove the on-hand row from the list. Only allowed when it's at zero —
        # the StockMovement ledger (append-only) keeps the history, so deleting
        # the cached level row is safe and just hides a now-empty line. Refuse to
        # delete a row that still holds stock, so real inventory can't vanish.
        from decimal import Decimal

        if (instance.quantity or Decimal("0")) != Decimal("0"):
            raise ValidationError({
                "detail": "Set the on-hand quantity to 0 before removing this "
                          "stock line (it still holds stock)."
            })
        instance.delete()


# ---------------------------------------------------------------------------
# Stock movements — read-only ledger
# ---------------------------------------------------------------------------
# Restock report — products at/below their reorder level
# ---------------------------------------------------------------------------


class RestockViewSet(_TenantQuerySetMixin, viewsets.ViewSet):
    """GET /api/inventory/restock/ — products that need reordering.

    A product needs restock when its CURRENT stock (summed across branches, or
    a single branch via ?branch=) is at or below the PRODUCT's reorder_level
    (the threshold operators set on the product form). reorder_level=0/null
    means "don't track" and is excluded. Returns shortfall + a suggested
    reorder quantity so the owner can act straight from the list.

    Query params: ?branch=<id> (per-branch view), ?q=<text> (name/sku),
    ?page / ?page_size (paginated).
    """

    permission_classes = [_INVENTORY_GATE, IsTenantMember]

    def list(self, request):
        from decimal import Decimal

        from django.db.models import DecimalField, F, Q, Sum, Value
        from django.db.models.functions import Coalesce

        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            return Response({"count": 0, "results": []})

        branch = request.query_params.get("branch")
        q = request.query_params.get("q")

        # Sum current stock per product (optionally scoped to one branch).
        level_filter = Q(stock_levels__variant__isnull=True)
        if branch:
            level_filter &= Q(stock_levels__branch_id=branch)

        products = (
            Product.objects.filter(
                tenant_id=tenant_id, deleted_at__isnull=True, is_active=True,
            )
            .exclude(reorder_level__isnull=True)
            .exclude(reorder_level=Decimal("0"))
            .annotate(
                on_hand=Coalesce(
                    Sum("stock_levels__quantity", filter=level_filter),
                    Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=4),
                ),
            )
            .filter(on_hand__lte=F("reorder_level"))
            .select_related("uom")
            .order_by("on_hand", "name")
        )
        if q:
            products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))

        # Simple pagination (mirrors StandardPagination defaults).
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            page_size = min(200, max(1, int(request.query_params.get("page_size", "50"))))
        except ValueError:
            page, page_size = 1, 50
        total = products.count()
        rows = products[(page - 1) * page_size: page * page_size]

        results = []
        for p in rows:
            reorder = p.reorder_level or Decimal("0")
            on_hand = p.on_hand or Decimal("0")
            shortfall = max(Decimal("0"), reorder - on_hand)
            suggested = p.reorder_quantity or shortfall or reorder
            results.append({
                "product_id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "uom": p.uom.code if p.uom_id else None,
                "on_hand": str(on_hand),
                "reorder_level": str(reorder),
                "shortfall": str(shortfall),
                "suggested_order_qty": str(suggested),
                "out_of_stock": on_hand <= 0,
            })
        return Response({"count": total, "page": page, "page_size": page_size, "results": results})


class ExpiryViewSet(viewsets.ViewSet):
    """GET /api/inventory/expiry/ — batches at/near expiry (pharmacy).

    Returns ProductBatch rows that still hold stock (current_quantity > 0) and
    whose expiry_date falls on or before today + `within` days (default 90),
    soonest first, each tagged with a bucket: 'expired', 'soon' (<=30d) or
    'upcoming' (<=window). Mirrors the Restock list shape so the UI reuses the
    same paginated-list scaffolding.

    Query params: ?within=<days>, ?branch=<id>, ?q=<name/sku/batch>,
    ?page / ?page_size.
    """

    permission_classes = [_INVENTORY_GATE, IsTenantMember]

    def list(self, request):
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            return Response({"count": 0, "results": []})

        try:
            within = max(0, int(request.query_params.get("within", "90")))
        except ValueError:
            within = 90
        today = timezone.localdate()
        cutoff = today + timedelta(days=within)

        qs = (
            ProductBatch.objects.filter(
                product__tenant_id=tenant_id,
                product__deleted_at__isnull=True,
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=cutoff,
            )
            .select_related("product", "product__uom", "branch")
            .order_by("expiry_date", "product__name")
        )
        if (branch := request.query_params.get("branch")):
            qs = qs.filter(branch_id=branch)
        if (q := request.query_params.get("q")):
            qs = qs.filter(
                Q(product__name__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(batch_number__icontains=q)
            )

        try:
            page = max(1, int(request.query_params.get("page", "1")))
            page_size = min(200, max(1, int(request.query_params.get("page_size", "50"))))
        except ValueError:
            page, page_size = 1, 50
        total = qs.count()
        rows = qs[(page - 1) * page_size: page * page_size]

        soon_cutoff = today + timedelta(days=30)
        results = []
        for b in rows:
            if b.expiry_date < today:
                bucket = "expired"
            elif b.expiry_date <= soon_cutoff:
                bucket = "soon"
            else:
                bucket = "upcoming"
            results.append({
                "batch_id": str(b.id),
                "product_id": str(b.product_id),
                "name": b.product.name,
                "sku": b.product.sku,
                "uom": b.product.uom.code if b.product.uom_id else None,
                "batch_number": b.batch_number,
                "expiry_date": b.expiry_date.isoformat(),
                "days_to_expiry": (b.expiry_date - today).days,
                "on_hand": str(b.current_quantity),
                "branch": b.branch.name if b.branch_id else None,
                "bucket": bucket,
            })
        return Response({"count": total, "page": page, "page_size": page_size, "results": results})


# ---------------------------------------------------------------------------


class StockMovementViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = StockMovement.objects.select_related(
        "product", "branch", "warehouse",
    ).order_by("-created_at")
    serializer_class = StockMovementSerializer
    permission_classes = [_STOCK_GATE, IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (p := params.get("product")):
            qs = qs.filter(product_id=p)
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (w := params.get("warehouse")):
            qs = qs.filter(warehouse_id=w)
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
    permission_classes = [_STOCK_GATE, HasRolePerm.with_perm("inventory.adjust")]

    def create(self, request):
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        try:
            branch = Branch.objects.for_tenant(request.tenant_id).get(pk=v["branch"])
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")

        # Optional warehouse (Digital Invoicing). Must belong to the posted
        # branch + tenant; when omitted the adjustment is branch-keyed (POS).
        warehouse = None
        if v.get("warehouse"):
            try:
                warehouse = Warehouse.objects.for_tenant(request.tenant_id).get(
                    pk=v["warehouse"], deleted_at__isnull=True,
                )
            except Warehouse.DoesNotExist:
                raise NotFound("Warehouse not found.")
            if warehouse.branch_id != branch.id:
                raise ValidationError(
                    {"warehouse": "Warehouse does not belong to the selected branch."}
                )

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

        mt = v["movement_type"]
        entered = v["quantity"]

        if mt == "opening_balance":
            # Opening balance is the ABSOLUTE target on-hand, not a delta. The
            # ledger only stores deltas (record_movement adds), so re-entering
            # the same opening balance would otherwise DOUBLE the stock. Compute
            # the delta from the current on-hand to the entered target and record
            # that — so opening balance is idempotent ("set to N", run as many
            # times as you like). Negative deltas are fine (correcting downward).
            from decimal import Decimal

            from django.db.models import Q

            current = (
                StockLevel.objects.filter(
                    tenant_id=request.tenant_id, product=product, variant=variant,
                )
                .filter(
                    Q(warehouse=warehouse) if warehouse is not None
                    else Q(branch=branch, warehouse__isnull=True)
                )
                .values_list("quantity", flat=True)
                .first()
            ) or Decimal("0")
            signed_qty = entered - current
            if signed_qty == 0:
                # Nothing to change — return the current level without writing a
                # no-op movement into the append-only ledger.
                return Response(
                    {"detail": "Opening balance already matches on-hand; no change.",
                     "quantity": str(entered)},
                    status=status.HTTP_200_OK,
                )
        else:
            # Sign convention: outflow types are stored negative.
            signed_qty = entered
            if mt in ("adjustment_out", "damage", "expiry") and signed_qty > 0:
                signed_qty = -signed_qty

        movement = record_movement(
            tenant_id=request.tenant_id,
            product=product,
            variant=variant,
            branch=branch,
            warehouse=warehouse,
            movement_type=mt,
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
    permission_classes = [_INVENTORY_GATE, HasRolePerm.with_perm("inventory.adjust")]

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
    permission_classes = [_INVENTORY_GATE, HasRolePerm.with_perm("inventory.adjust")]

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


# ---------------------------------------------------------------------------
# Warehouses (Digital Invoicing) — CRUD over godowns under a branch
# ---------------------------------------------------------------------------


class WarehouseViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    """Manage warehouses (godowns) for Digital-Invoicing tenants.

    Gated on the `warehouses` module, so POS tenants never reach it. Soft
    deletes (sets deleted_at) and refuses to delete a warehouse that still
    holds stock, so on-hand history is never orphaned.
    """

    queryset = (
        Warehouse.objects.select_related("branch")
        .filter(deleted_at__isnull=True)
        .order_by("branch__name", "name")
    )
    serializer_class = WarehouseSerializer
    permission_classes = [_WAREHOUSE_GATE, HasRolePerm.with_perm("inventory.adjust")]

    def _validate_branch(self, branch_id):
        try:
            return Branch.objects.for_tenant(self.request.tenant_id).get(
                pk=branch_id, deleted_at__isnull=True,
            )
        except Branch.DoesNotExist:
            raise ValidationError({"branch": "Branch not found for this tenant."})

    @action(detail=False, methods=["get"], url_path="branches")
    def branches(self, request):
        """List this tenant's branches so the warehouse form can attach a
        warehouse to one. Gated on the same `warehouses` module — DI tenants
        don't have the `branches` module, so they can't use /branches/ but
        still need to see their (often implicit) branch here.
        """
        rows = (
            Branch.objects.for_tenant(request.tenant_id)
            .filter(deleted_at__isnull=True)
            .order_by("name")
            .values("id", "name", "code")
        )
        return Response(list(rows))

    def perform_create(self, serializer):
        branch = self._validate_branch(serializer.validated_data["branch"].id)
        with transaction.atomic():
            # "Set default" is exclusive within a branch — clear any prior one.
            if serializer.validated_data.get("is_default"):
                Warehouse.objects.filter(
                    branch=branch, is_default=True, deleted_at__isnull=True,
                ).update(is_default=False)
            serializer.save(tenant_id=self.request.tenant_id)

    def perform_update(self, serializer):
        instance = serializer.instance
        becomes_default = serializer.validated_data.get("is_default")
        with transaction.atomic():
            if becomes_default and not instance.is_default:
                Warehouse.objects.filter(
                    branch=instance.branch, is_default=True, deleted_at__isnull=True,
                ).exclude(pk=instance.pk).update(is_default=False)
            serializer.save()

    def perform_destroy(self, instance):
        from decimal import Decimal

        has_stock = StockLevel.objects.filter(
            warehouse=instance, quantity__gt=Decimal("0"),
        ).exists()
        if has_stock:
            raise ValidationError(
                {"detail": "Cannot delete a warehouse that still holds stock. "
                           "Move or zero out its stock first."}
            )
        from django.utils import timezone
        instance.deleted_at = timezone.now()
        instance.is_default = False
        instance.save(update_fields=["deleted_at", "is_default", "updated_at"])
