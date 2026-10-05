"""Restaurant API — gated on the `restaurant` module + owner/manager perms.

Tables + modifier catalog are CRUD ViewSets. Kitchen/floor are read+action
endpoints over held sales.Invoices (orders are invoices, not a separate model).
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasModule, HasRolePerm, IsTenantMember
from apps.sales.models import Invoice, SaleItem

from . import services
from .models import MenuItemModifierGroup, Modifier, ModifierGroup, Table
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

    def get_queryset(self):
        qs = super().get_queryset()
        # ?product=<id> → only the groups attached to that menu item (via
        # MenuItemModifierGroup). The terminal's modifier picker relies on this
        # so it shows ONLY the item's own options, not every group in the tenant.
        if (product := self.request.query_params.get("product")):
            qs = qs.filter(product_links__product_id=product).order_by(
                "product_links__display_order", "display_order",
            ).distinct()
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


class ProductModifierGroupsView(APIView):
    """Attach modifier groups to a menu item.

    GET /api/restaurant/products/<product_id>/modifier-groups/ → ordered group ids
    PUT same → replace the product's attached groups with the posted id list.
    Used by the admin product-edit "Modifiers" card.
    """
    permission_classes = [_RESTAURANT_GATE, HasRolePerm.with_perm("products.manage")]

    def _product(self, request, product_id):
        from apps.catalog.models import Product
        p = Product.objects.for_tenant(request.tenant_id).filter(pk=product_id).first()
        if not p:
            raise NotFound("Product not found.")
        return p

    def get(self, request, product_id):
        p = self._product(request, product_id)
        links = p.modifier_links.order_by("display_order")
        return Response({"group_ids": [str(l.group_id) for l in links]})

    def put(self, request, product_id):
        p = self._product(request, product_id)
        ids = request.data.get("group_ids", [])
        if not isinstance(ids, list):
            raise ValidationError({"group_ids": "Expected a list."})
        valid = set(
            ModifierGroup.objects.filter(
                tenant_id=request.tenant_id, deleted_at__isnull=True, pk__in=ids,
            ).values_list("id", flat=True)
        )
        p.modifier_links.all().delete()
        accepted = []
        for order, gid in enumerate(ids):
            g = _coerce_uuid(gid)
            if g in valid:
                MenuItemModifierGroup.objects.create(product=p, group_id=g, display_order=order)
                accepted.append(str(g))
        return Response({"group_ids": accepted})


def _coerce_uuid(v):
    from uuid import UUID
    try:
        return UUID(str(v))
    except (ValueError, TypeError):
        return None


def _order_payload(inv: Invoice) -> dict:
    """Compact order shape for the floor + KDS views."""
    return {
        "id": str(inv.id),
        "local_invoice_number": inv.local_invoice_number,
        "order_type": inv.order_type,
        "order_status": inv.order_status,
        # Cashier's free-text reference (set via "Save order"), shown in the
        # Open-orders list so a parked order is recognisable at a glance.
        "held_label": inv.held_label,
        "table": inv.table.name if inv.table_id else None,
        "table_id": str(inv.table_id) if inv.table_id else None,
        "covers": inv.covers,
        "kitchen_sent_at": inv.kitchen_sent_at.isoformat() if inv.kitchen_sent_at else None,
        "grand_total": str(inv.grand_total),
        # True when this order was fired from a shared waiter tablet (not a
        # cashier till) — lets the POS badge it "from waiter" so the cashier can
        # tell a floor-fired order apart from their own parked ticket.
        "from_waiter_tablet": bool(
            inv.terminal_id and inv.terminal.is_order_taking_only
        ),
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


def _kot_relay_payload(inv: Invoice) -> dict:
    """A KOT ticket for the branch terminal to PRINT — only the fired-but-not-yet-
    printed food lines (rooms excluded). is_additional flags a follow-up ticket
    (course 2) when some of this order's lines were already printed."""
    unprinted = (
        inv.items.filter(
            sent_to_kitchen=True, kot_printed_at__isnull=True, is_cancelled=False,
        )
        .exclude(product__category__name="Rooms")
        .order_by("line_number")
    )
    already_printed_before = inv.items.filter(kot_printed_at__isnull=False).exists()
    return {
        "id": str(inv.id),
        "order_number": inv.local_invoice_number,
        "order_type": inv.order_type or "dine_in",
        "table_name": inv.table.name if inv.table_id else None,
        "covers": inv.covers,
        "reference": inv.held_label or (inv.buyer_name or None),
        "is_additional": already_printed_before,
        "items": [
            {
                "product_name": it.product_name,
                "quantity": str(it.quantity),
                "modifiers": [{"name": m.get("name")} for m in (it.modifiers or [])],
                "item_note": it.item_note,
            }
            for it in unprinted
        ],
        "item_ids": [str(it.id) for it in unprinted],
    }


def _relay_tenant_id(request):
    """Resolve the tenant for a KOT-relay call, authenticating EITHER way:

      - a signed-in user (request.tenant_id set by the JWT middleware), OR
      - a PAIRED DEVICE presenting terminal_id + device_fingerprint (same trust
        model as /terminals/roster/).

    The device path is what lets a branch print KOTs the moment the till is
    PAIRED — without waiting for a cashier to log in. Kitchen printing must not
    depend on someone being signed into the printer terminal. Returns the
    tenant_id, or raises if neither credential is valid.
    """
    tenant_id = getattr(request, "tenant_id", None)
    if tenant_id is not None:
        return tenant_id
    # Device-trust fallback (query for GET, body for POST).
    src = request.query_params if request.method == "GET" else request.data
    terminal_id = (src.get("terminal_id") or "").strip()
    fingerprint = (src.get("device_fingerprint") or "").strip()
    if not terminal_id or not fingerprint:
        raise NotAuthenticated(
            "Sign in, or provide the paired terminal_id + device_fingerprint.",
        )
    from apps.tenants.models import Terminal
    terminal = (
        Terminal.objects.filter(
            pk=terminal_id, device_fingerprint=fingerprint, is_active=True,
        ).first()
    )
    if terminal is None:
        raise NotAuthenticated("This device is not paired.")
    return terminal.tenant_id


class KdsUnprintedView(APIView):
    """GET /api/restaurant/kds/unprinted/?branch=<id> — orders with fired,
    not-yet-printed lines. The branch's Electron terminal(s) poll this to RELAY
    KOTs for orders fired from a waiter tablet (which has no printer).

    Auth: a signed-in cashier OR a paired device (terminal_id + device_fingerprint
    query params). The device path means kitchen printing works as soon as the
    till is paired, even before any cashier logs in."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        tenant_id = _relay_tenant_id(request)
        branch_id = request.query_params.get("branch")
        if not branch_id:
            raise ValidationError({"branch": "Required."})
        orders = (
            services.open_orders_qs(tenant_id, branch_id=branch_id)
            .filter(order_status__in=["sent_to_kitchen", "ready"])
            .filter(
                items__sent_to_kitchen=True,
                items__kot_printed_at__isnull=True,
                items__is_cancelled=False,
            )
            .distinct()
        )
        payloads = [_kot_relay_payload(o) for o in orders]
        # A row can match the filter but have all its unprinted lines be rooms —
        # drop those (nothing to print).
        payloads = [p for p in payloads if p["items"]]
        return Response({"orders": payloads})


class MarkKotPrintedView(APIView):
    """POST /api/restaurant/orders/<id>/mark-printed/  body {"item_ids":[...]}.
    Stamps kot_printed_at on exactly those lines, conditioned on IS NULL — so a
    retry (lost ack) or two terminals racing both no-op past the first winner.
    This single atomic conditional UPDATE is the print-exactly-once guard.

    Auth: signed-in cashier OR paired device (terminal_id + device_fingerprint in
    the body), matching KdsUnprintedView so the relay can ack without a login."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, pk):
        tenant_id = _relay_tenant_id(request)
        item_ids = request.data.get("item_ids") or []
        if not item_ids:
            raise ValidationError({"item_ids": "Required."})
        now = timezone.now()
        updated = SaleItem.objects.filter(
            invoice_id=pk, invoice__tenant_id=tenant_id,
            id__in=item_ids, kot_printed_at__isnull=True,
        ).update(kot_printed_at=now)
        Invoice.objects.filter(pk=pk, tenant_id=tenant_id).update(
            kitchen_printed_at=now,
        )
        return Response({"marked": updated}, status=status.HTTP_200_OK)


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


def _order_detail_payload(inv: Invoice) -> dict:
    """Fuller payload for the terminal to RESUME an order — includes the data
    the cashier needs to rebuild the cart (product ids, unit prices, modifiers)."""
    base = _order_payload(inv)
    base["cart_lines"] = [
        {
            # Line id + print state let the firing till ack its OWN KOT print
            # via mark-printed/. Without them kot_printed_at stayed NULL, the
            # relay saw the lines as unprinted and printed a SECOND slip.
            "id": str(it.id),
            "kot_printed": it.kot_printed_at is not None,
            "product": str(it.product_id),
            "product_name": it.product_name,
            "product_sku": it.product_sku,
            "uom_code": it.uom_code,
            "hs_code": it.hs_code,
            "quantity": str(it.quantity),
            "unit_price": str(it.unit_price),
            "discount_pct": str(it.discount_pct),
            "discount_amount": str(it.discount_amount),
            "tax_rate": str(it.tax_rate),
            "modifiers": it.modifiers or [],
            "item_note": it.item_note,
            "course": it.course,
            "sent_to_kitchen": it.sent_to_kitchen,
        }
        for it in inv.items.all().order_by("line_number")
    ]
    base["client_uuid"] = str(inv.client_uuid)
    base["customer_id"] = str(inv.customer_id) if inv.customer_id else None
    return base


class OpenOrderView(APIView):
    """Open (held, unpaid) restaurant orders — the live order book.

    GET  /api/restaurant/orders/         → list open orders (terminal table list)
    GET  /api/restaurant/orders/?id=<id> → one order, with cart_lines to resume
    POST /api/restaurant/orders/         → create/update an open order (fire
         kitchen). Idempotent on client_uuid. Body = the same cart payload the
         terminal sends to checkout (product/quantity/unit_price/modifiers/…)
         plus order_type/table/covers/customer.

    NB: an open order is CLOSED by Charge, not here — create_invoice (the
    checkout finalizer, keyed on the same client_uuid) flips is_held=False on
    the very same row, which drops it from open_orders_qs. There is deliberately
    no separate un-hold endpoint: closing before that finalizer runs would make
    it mistake the row for an already-paid duplicate and skip payments/stock/FBR.
    """
    permission_classes = [_RESTAURANT_GATE, IsTenantMember]

    def get(self, request):
        if (oid := request.query_params.get("id")):
            inv = Invoice.objects.for_tenant(request.tenant_id).filter(pk=oid).first()
            if not inv:
                raise NotFound("Order not found.")
            # Terminal ownership: a till may only resume its OWN open order. This
            # is what makes a table read "occupied but not openable" on another
            # terminal (the floor view still shows occupancy branch-wide, but the
            # order itself belongs to the terminal that opened it). Admin/KDS
            # callers omit `terminal` and can read any order.
            req_terminal = request.query_params.get("terminal")
            if req_terminal and str(inv.terminal_id) != req_terminal:
                # HANDOFF EXCEPTION: an order fired from a shared "waiter tablet"
                # terminal (is_order_taking_only) has no till of its own to charge
                # it, so any cashier till in the branch MUST be able to resume it.
                # For those the cross-terminal block is exactly the wrong behaviour
                # — relax it. All other orders stay till-private.
                order_taking = bool(
                    inv.terminal_id and inv.terminal.is_order_taking_only
                )
                if not order_taking:
                    raise NotFound("Order not found.")
            return Response(_order_detail_payload(inv))
        branch_id = request.query_params.get("branch")
        # Terminal-scoped: a till sees only its OWN open orders (each terminal
        # owns its sales). Admin/KDS callers omit `terminal` to see the branch.
        terminal_id = request.query_params.get("terminal")
        orders = services.open_orders_qs(
            request.tenant_id, branch_id=branch_id, terminal_id=terminal_id,
        )
        return Response({"orders": [_order_payload(o) for o in orders]})

    def post(self, request):
        from apps.tenants.models import Branch, Terminal

        payload = request.data
        if not payload.get("client_uuid"):
            raise ValidationError({"client_uuid": "Required."})
        if not payload.get("terminal") or not payload.get("branch"):
            raise ValidationError({"detail": "branch and terminal are required."})
        branch = Branch.objects.for_tenant(request.tenant_id).filter(pk=payload["branch"]).first()
        terminal = Terminal.objects.for_tenant(request.tenant_id).filter(pk=payload["terminal"]).first()
        if not branch or not terminal:
            raise NotFound("Branch or terminal not found.")
        invoice = services.upsert_open_order(
            tenant_id=request.tenant_id, branch=branch, terminal=terminal,
            cashier=request.user, payload=payload, request=request,
        )
        return Response(_order_detail_payload(invoice), status=status.HTTP_200_OK)

    def delete(self, request):
        """Void (soft-delete) an open order so it leaves the book.

        Called when a resumed open order has all its items removed (an empty
        order is a voided order). Keyed on client_uuid. Idempotent: an unknown,
        already-voided, or already-paid order returns 200 with voided=false so a
        retry never errors.
        """
        client_uuid = request.query_params.get("client_uuid") or request.data.get("client_uuid")
        if not client_uuid:
            raise ValidationError({"client_uuid": "Required."})
        invoice = services.void_open_order(
            tenant_id=request.tenant_id, client_uuid=client_uuid,
            user=request.user, request=request,
        )
        return Response({"voided": invoice is not None}, status=status.HTTP_200_OK)
