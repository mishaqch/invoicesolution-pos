"""Catalog API views.

ViewSets enforce tenant scope at the queryset layer (defense in depth: even
if the view is misconfigured, the queryset filter rejects). Permissions per
the role matrix in DATABASE_SCHEMA.md §1.
"""

from __future__ import annotations

from django.db.models import Q
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import HasRolePerm, IsTenantMember

from .csv_import import build_dry_run_summary, commit_import, parse_csv
from .models import (
    Category,
    HsCode,
    Product,
    ProductBatch,
    ProductVariant,
    TaxRate,
    UnitOfMeasure,
)
from .serializers import (
    CategorySerializer,
    HsCodeSerializer,
    ProductBatchPosSerializer,
    ProductBatchSerializer,
    ProductPosSerializer,
    ProductSerializer,
    ProductVariantSerializer,
    TaxRateSerializer,
    UnitOfMeasureSerializer,
)


class _TenantQuerySetMixin:
    """Apply tenant filtering to every queryset on a tenant-scoped viewset."""

    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Global lookups (no tenancy)
# ---------------------------------------------------------------------------


class UnitOfMeasureViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class HsCodeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = HsCode.objects.all()
    serializer_class = HsCodeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["code", "description"]

    @action(detail=False, methods=["get"], url_path="meta")
    def meta(self, request):
        """Summary metadata for the HS-code catalog.

        Returns the total count + the last `sync_pral_reference` run
        timestamp so the catalog page can show users 'X codes, last
        synced Y ago' instead of stale placeholder copy.
        """
        from django.core.cache import cache
        synced_at = cache.get("catalog:pral_reference_synced_at")
        return Response({
            "count": HsCode.objects.count(),
            "last_synced_at": synced_at,
        })


# ---------------------------------------------------------------------------
# Tenant-scoped
# ---------------------------------------------------------------------------


class TaxRateViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [HasRolePerm.with_perm("settings.business_profile")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class CategoryViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("display_order", "name")
    serializer_class = CategorySerializer
    permission_classes = [HasRolePerm.with_perm("products.manage")]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class ProductViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = (
        Product.objects.filter(deleted_at__isnull=True)
        .select_related("category", "uom", "tax_rate", "hs_code")
    )
    serializer_class = ProductSerializer
    permission_classes = [HasRolePerm.with_perm("products.manage")]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["sku", "barcode", "name", "name_ur"]
    ordering_fields = ["name", "sku", "sale_price", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (cat := params.get("category")):
            qs = qs.filter(category_id=cat)
        if (active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        if (taxable := params.get("taxable")) is not None:
            qs = qs.filter(is_taxable=taxable.lower() in ("1", "true", "yes"))
        if (low_stock := params.get("low_stock")) and low_stock.lower() in ("1", "true"):
            qs = qs.filter(
                Q(stock_levels__quantity__lte=models_F("reorder_level"))
                | Q(stock_levels__quantity__lte=models_F("stock_levels__reorder_level"))
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id, created_by=self.request.user)

    def perform_destroy(self, instance):
        from django.utils import timezone
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])

    @action(detail=False, methods=["post"], url_path="import",
            parser_classes=[MultiPartParser, FormParser])
    def import_csv(self, request):
        """CSV import: ?dry_run=true returns counts + errors; otherwise commits."""
        if "file" not in request.FILES:
            raise ValidationError({"file": "A CSV file is required."})

        rows, parse_errors = parse_csv(request.FILES["file"])
        dry_run = request.query_params.get("dry_run", "").lower() in ("1", "true", "yes")

        if dry_run:
            summary = build_dry_run_summary(
                tenant_id=request.tenant_id, rows=rows, parse_errors=parse_errors
            )
            return Response(summary)

        if parse_errors:
            return Response(
                {"detail": "CSV failed validation; run with ?dry_run=true to inspect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = commit_import(
            tenant_id=request.tenant_id,
            user=request.user,
            rows=rows,
        )
        return Response(result, status=status.HTTP_201_CREATED)


class ProductVariantViewSet(viewsets.ModelViewSet):
    """Variants live under their parent product's tenant."""
    queryset = ProductVariant.objects.select_related("product").all()
    serializer_class = ProductVariantSerializer
    permission_classes = [HasRolePerm.with_perm("products.manage")]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(product__tenant_id=tenant_id)


class ProductBatchViewSet(viewsets.ModelViewSet):
    """Per-product stock batches (pharmacy + date-sensitive goods).

    `GET /api/catalog/batches/?product=<id>` lists a product's batches, soonest
    expiry first. Creating a batch is an *opening-stock* event for that batch:
    we set current_quantity = initial_quantity and append an `opening_balance`
    StockMovement so the aggregate StockLevel stays consistent (record_movement
    is the only sanctioned way to move stock).
    """
    queryset = ProductBatch.objects.select_related("product", "branch").all()
    serializer_class = ProductBatchSerializer
    permission_classes = [HasRolePerm.with_perm("inventory.adjust")]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        qs = qs.filter(product__tenant_id=tenant_id, product__deleted_at__isnull=True)
        if (product := self.request.query_params.get("product")):
            qs = qs.filter(product_id=product)
        # Soonest-expiry first (nulls last) — the order a pharmacist scans for.
        return qs.order_by("expiry_date", "batch_number")

    def perform_create(self, serializer):
        from decimal import Decimal

        from apps.inventory.services.movements import record_movement

        tenant_id = self.request.tenant_id
        qty = Decimal(str(serializer.validated_data["initial_quantity"]))
        # Start the batch at 0 and let record_movement bring current_quantity up
        # to the opening qty — record_movement is the single source of truth for
        # batch quantity (it bumps both the batch counter AND the aggregate
        # StockLevel). Setting current_quantity here too would double-count.
        batch = serializer.save(current_quantity=Decimal("0"))
        if batch.branch_id and qty:
            record_movement(
                tenant_id=tenant_id,
                product=batch.product,
                branch=batch.branch,
                batch=batch,
                movement_type="opening_balance",
                quantity=qty,
                unit_cost=batch.cost_price,
                reference_type="product_batch",
                reference_id=batch.id,
                reason=f"Batch {batch.batch_number} opening stock",
                performed_by=self.request.user,
            )
            # record_movement updated a re-fetched row; refresh so the response
            # serializes the new current_quantity (not the 0 we saved above).
            batch.refresh_from_db(fields=["current_quantity"])
        else:
            # No branch (can't record a movement) — set the counter directly so
            # the batch still reflects its opening quantity.
            batch.current_quantity = qty
            batch.save(update_fields=["current_quantity"])


# ---------------------------------------------------------------------------
# POS sync endpoint (read-only mirror)
# ---------------------------------------------------------------------------


class CatalogSyncView(viewsets.ViewSet):
    """`GET /api/catalog/sync/?since=<iso>` returns products + categories.

    Phase 1: paged sync, no fancy cursor; if `since` is provided, returns
    rows with updated_at >= since (including soft-deleted to support tombstone
    handling on the POS).
    """
    permission_classes = [IsTenantMember]

    def list(self, request):
        since = request.query_params.get("since")

        product_qs = Product.objects.filter(tenant_id=request.tenant_id)
        category_qs = Category.objects.filter(tenant_id=request.tenant_id)
        if since:
            product_qs = product_qs.filter(updated_at__gte=since)
            category_qs = category_qs.filter(updated_at__gte=since)

        # Batches for FEFO at the terminal. Unlike products/categories these
        # have no updated_at and their current_quantity changes on every sale,
        # so an incremental `since` filter would miss depletions — we always
        # send the FULL current set of in-stock batches for batch-tracked
        # products (far fewer rows than the product catalog). The terminal
        # replaces its batch table from this snapshot.
        batch_qs = ProductBatch.objects.filter(
            product__tenant_id=request.tenant_id,
            product__deleted_at__isnull=True,
            product__is_batch_tracked=True,
            current_quantity__gt=0,
        ).order_by("expiry_date")

        return Response({
            "products": ProductPosSerializer(product_qs, many=True).data,
            "categories": CategorySerializer(category_qs, many=True).data,
            "batches": ProductBatchPosSerializer(batch_qs, many=True).data,
            # Tells the terminal this is the complete batch set (replace, not merge).
            "batches_full_snapshot": True,
        })


# Tiny helpers to avoid django.db.models.F import noise inline.
from django.db import models  # noqa: E402
def models_F(name):  # noqa: N802
    return models.F(name)
