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

# Stock-IN movement types — these BRING stock in for sale, so the item must be
# FBR-ready (HS code, UoM, sale type set) before it can be stocked. Outflow
# types (adjustment_out / damage / expiry) are intentionally NOT gated: you must
# always be able to reduce/write off stock, even for an incomplete product.
_STOCK_IN_TYPES = frozenset(
    {"opening_balance", "adjustment_in", "purchase", "transfer_in"}
)


def _missing_fbr_fields(product) -> list[str]:
    """Which FBR-identity fields a product is still missing.

    Every invoice line submitted to PRAL carries hsCode, uoM and a saleType; a
    product without them produces an invoice FBR rejects (e.g. errorCode 0052 /
    0204). We gate stock-IN on these three so an item can't be stocked-for-sale
    until its fiscal identity is complete — surfacing the gap at stock-in (where
    the owner is already in the FBR cockpit) rather than at submission time.
    """
    missing = []
    if not product.hs_code_id:
        missing.append("HS code")
    if not product.uom_id:
        missing.append("Unit of measure")
    if not (product.sale_type or "").strip():
        missing.append("FBR sale type")
    return missing


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

    def _opening_map(self, rows):
        """Map {stock_level_id: opening_qty} for the given StockLevel rows.

        "Opening" is the on-hand each line started its CURRENT run with — a
        running-balance concept that a single SQL subquery can't express (it
        must drop reversed/abandoned runs like a typo'd opening balance that was
        later zeroed). So we pull every movement for the visible products in ONE
        query, bucket them by (product, branch, warehouse) and replay each
        ledger through compute_opening(). One extra query for the whole page —
        no N+1.
        """
        from collections import defaultdict

        from .services.movements import compute_opening

        if not rows:
            return {}
        product_ids = {r.product_id for r in rows}
        tenant_id = getattr(self.request, "tenant_id", None)
        moves = (
            StockMovement.objects.filter(
                tenant_id=tenant_id, product_id__in=product_ids,
            )
            .order_by("created_at", "id")
            .values("product_id", "branch_id", "warehouse_id", "movement_type", "quantity")
        )
        # Bucket movements by the SAME key a StockLevel is unique on.
        buckets: dict[tuple, list] = defaultdict(list)
        for m in moves:
            key = (m["product_id"], m["branch_id"], m["warehouse_id"])
            buckets[key].append(
                type("M", (), {"movement_type": m["movement_type"], "quantity": m["quantity"]})()
            )
        out = {}
        for r in rows:
            key = (r.product_id, r.branch_id, r.warehouse_id)
            out[r.id] = compute_opening(buckets.get(key, []))
        return out

    def list(self, request, *args, **kwargs):
        # Compute "opening" per row for the current page and stash it on each
        # instance so the serializer can read it (one bulk movement query).
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        opening_map = self._opening_map(rows)
        for r in rows:
            r._opening = opening_map.get(r.id)
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

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

    @action(detail=False, methods=["get"], url_path="card")
    def card(self, request):
        """GET /api/inventory/stock-levels/card/?product=&warehouse=&branch=

        The "stock card" for one product at one location: the number a
        shopkeeper actually wants — what you OPENED with, total IN, total OUT,
        and what you have NOW — plus a running-balance ledger of every movement
        (newest first) so "where did my stock go?" is answerable in one screen.

        Opening = the FIRST `opening_balance` movement for this product+location
        (the on-hand you started this line with). Everything after it is the
        running history. Scope is warehouse-keyed when ?warehouse is given
        (Digital Invoicing), else branch-keyed (POS) when ?branch is given.
        """
        from decimal import Decimal

        tenant_id = getattr(request, "tenant_id", None)
        product_id = request.query_params.get("product")
        if not tenant_id or not product_id:
            raise ValidationError({"product": "A product id is required."})

        warehouse_id = request.query_params.get("warehouse")
        branch_id = request.query_params.get("branch")

        moves = StockMovement.objects.filter(
            tenant_id=tenant_id, product_id=product_id,
        )
        if warehouse_id:
            moves = moves.filter(warehouse_id=warehouse_id)
        elif branch_id:
            moves = moves.filter(branch_id=branch_id, warehouse__isnull=True)
        # Chronological for the running balance; we reverse for display.
        moves = list(
            moves.select_related("performed_by").order_by("created_at", "id")
        )

        # Opening = on-hand the CURRENT stock run started with (see
        # compute_opening): the balance right after the first stock-in that
        # began the stock held today, ignoring reversed/abandoned runs (e.g. a
        # typo'd opening_balance that was later zeroed). opening_at is when that
        # run started.
        from .services.movements import compute_opening

        opening = compute_opening(moves) or Decimal("0")
        opening_at = None
        running = Decimal("0")
        for m in moves:
            prev = running
            running += m.quantity or Decimal("0")
            if (
                m.movement_type in ("opening_balance", "adjustment_in", "purchase", "transfer_in")
                and prev <= Decimal("0")
                and running > Decimal("0")
            ):
                opening_at = m.created_at

        total_in = sum(
            (m.quantity for m in moves
             if (m.quantity or Decimal("0")) > 0
             and m.movement_type != "opening_balance"),
            Decimal("0"),
        )
        total_out = sum(
            (m.quantity for m in moves if (m.quantity or Decimal("0")) < 0),
            Decimal("0"),
        )

        # Running balance, computed forward then attached to each row.
        running = Decimal("0")
        ledger = []
        for m in moves:
            running += m.quantity or Decimal("0")
            ledger.append({
                "id": str(m.id),
                "movement_type": m.movement_type,
                "quantity": str(m.quantity),
                "balance_after": str(running),
                "reason": m.reason or "",
                "reference_type": m.reference_type,
                "reference_id": str(m.reference_id) if m.reference_id else None,
                # User model is email-keyed (no get_full_name/username); show
                # the person's name, falling back to their email.
                "performed_by": (
                    m.performed_by.full_name or m.performed_by.email
                ) if m.performed_by_id else None,
                "created_at": m.created_at.isoformat(),
            })
        ledger.reverse()  # newest first for display

        return Response({
            "product": str(product_id),
            "warehouse": warehouse_id,
            "branch": branch_id,
            "opening": str(opening),
            "opening_at": opening_at.isoformat() if opening_at else None,
            "total_in": str(total_in),
            "total_out": str(abs(total_out)),
            "current": str(running),
            "ledger": ledger,
        })


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


class FbrReadinessViewSet(viewsets.ViewSet):
    """GET /api/inventory/fbr-readiness/ — products not yet invoice-ready.

    Lists live products whose FBR fiscal identity is incomplete, so an invoice
    line for them would be rejected by PRAL. Each row says exactly what's
    missing so the owner can clear the backlog in one place (and the stock-in
    gate stops blocking them). Same paginated-list shape as Restock/Expiry.

    A product is "not ready" when any of these is true:
      - no HS code            (PRAL errorCode 0052)
      - no UoM                (every line carries uoM)
      - no/blank sale type    (PRAL errorCode 0204)
      - an SRO schedule is set but the item serial is blank (FBR pairs them)
      - 3rd-Schedule but no retail price > 0 (PRAL errorCode 0122)

    Gated on EITHER module (POS `inventory` or DI `warehouses`) because both
    kinds of tenant submit to FBR. Query params: ?q=<name/sku>, ?page/?page_size.
    """

    permission_classes = [_STOCK_GATE, IsTenantMember]

    def list(self, request):
        from decimal import Decimal

        from django.db.models import Q

        tenant_id = getattr(request, "tenant_id", None)
        if not tenant_id:
            return Response({"count": 0, "results": []})

        # "Incomplete" = any required FBR field missing. Express as an OR of the
        # individual gaps so the DB does the filtering (no full-table Python loop).
        incomplete = (
            Q(hs_code__isnull=True)
            | Q(uom__isnull=True)
            | Q(sale_type__isnull=True)
            | Q(sale_type="")
            # SRO schedule set but serial blank (or vice-versa is fine — serial
            # alone isn't required), so flag schedule-without-serial.
            | (~Q(sro_schedule_no="") & Q(sro_item_serial_no=""))
            # 3rd-Schedule needs a retail price > 0.
            | (Q(is_third_schedule=True) & (Q(retail_price__isnull=True) | Q(retail_price__lte=Decimal("0"))))
        )
        products = (
            Product.objects.filter(
                tenant_id=tenant_id, deleted_at__isnull=True, is_active=True,
            )
            .filter(incomplete)
            .select_related("uom")
            .order_by("name")
        )
        if (q := request.query_params.get("q")):
            products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))

        try:
            page = max(1, int(request.query_params.get("page", "1")))
            page_size = min(200, max(1, int(request.query_params.get("page_size", "50"))))
        except ValueError:
            page, page_size = 1, 50
        total = products.count()
        rows = products[(page - 1) * page_size: page * page_size]

        results = []
        for p in rows:
            missing = []
            if not p.hs_code_id:
                missing.append("HS code")
            if not p.uom_id:
                missing.append("Unit of measure")
            if not (p.sale_type or "").strip():
                missing.append("FBR sale type")
            if (p.sro_schedule_no or "").strip() and not (p.sro_item_serial_no or "").strip():
                missing.append("SRO item serial no")
            if p.is_third_schedule and not (p.retail_price and p.retail_price > Decimal("0")):
                missing.append("Retail price")
            results.append({
                "product_id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "hs_code": p.hs_code_id,
                "uom": p.uom.code if p.uom_id else None,
                "sale_type": p.sale_type or None,
                "missing": missing,
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

        # FBR-readiness gate: a product can't be stocked FOR SALE until its
        # fiscal identity (HS code, UoM, sale type) is complete. Only applies to
        # stock-IN (and only when the entered quantity actually adds stock —
        # setting an opening balance to 0 or correcting downward is allowed so
        # the owner is never trapped). Manage the missing fields from the
        # "FBR details" panel on this same Stock screen.
        if mt in _STOCK_IN_TYPES:
            adds_stock = mt != "opening_balance" or entered > 0
            if adds_stock and (missing := _missing_fbr_fields(product)):
                raise ValidationError({
                    "detail": (
                        f"“{product.name}” is missing required FBR details: "
                        f"{', '.join(missing)}. Set them via “FBR details” on "
                        f"this product before adding stock for sale."
                    ),
                    "missing_fbr_fields": missing,
                })

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
