"""Sales API.

POST /api/sales/invoices/checkout/      — atomic checkout (create invoice)
GET  /api/sales/invoices/               — list (filterable)
GET  /api/sales/invoices/<id>/          — detail
POST /api/sales/invoices/<id>/hold/     — flip is_held + label
POST /api/sales/invoices/<id>/recall/   — flip is_held off
POST /api/sales/invoices/<id>/cancel/   — manual cancel (manager+; Phase 4 enforces FBR rules)

POST /api/sales/cash-sessions/open/
POST /api/sales/cash-sessions/<id>/close/
GET  /api/sales/cash-sessions/<id>/x-report/  — running totals for the open or recently closed session
"""

from __future__ import annotations

from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.accounts.permissions import HasRolePerm, IsTenantMember
from apps.customers.models import Customer
from apps.tenants.models import Branch, CashSession, Terminal

from .models import Invoice
from .serializers import (
    CancelSerializer,
    CheckoutSerializer,
    HoldSerializer,
    InvoiceSerializer,
    SessionCloseSerializer,
    SessionOpenSerializer,
)
from .services import cancellation, checkout, holds, sessions


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class InvoiceViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Invoice.objects
        .select_related("branch", "terminal", "cashier", "customer")
        .prefetch_related("items", "payments")
        .order_by("-invoice_date", "-created_at")
    )
    serializer_class = InvoiceSerializer
    permission_classes = [IsTenantMember]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["invoice_date", "grand_total", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (t := params.get("terminal")):
            qs = qs.filter(terminal_id=t)
        if (c := params.get("cashier")):
            qs = qs.filter(cashier_id=c)
        if (cust := params.get("customer")):
            qs = qs.filter(customer_id=cust)
        if (st := params.get("status")):
            qs = qs.filter(status=st)
        if (start := params.get("from")):
            qs = qs.filter(invoice_date__gte=start)
        if (end := params.get("to")):
            qs = qs.filter(invoice_date__lte=end)
        if (held := params.get("held")):
            qs = qs.filter(is_held=held.lower() in ("1", "true"))
        return qs

    @action(detail=False, methods=["post"], url_path="checkout",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def checkout(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        branch = self._fetch_tenant_object(Branch, v["branch"])
        terminal = self._fetch_tenant_object(Terminal, v["terminal"])
        session = (
            CashSession.objects.for_tenant(request.tenant_id).filter(
                pk=v.get("cash_session"),
            ).first()
            if v.get("cash_session") else None
        )
        customer = (
            Customer.objects.for_tenant(request.tenant_id).filter(
                pk=v.get("customer"),
            ).first()
            if v.get("customer") else None
        )

        invoice = checkout.create_invoice(
            tenant_id=request.tenant_id,
            branch=branch,
            terminal=terminal,
            cashier=request.user,
            cash_session=session,
            customer=customer,
            cart_lines=[dict(line) for line in v["cart_lines"]],
            cart_discount_pct=v.get("cart_discount_pct", 0),
            payments=[dict(p) for p in v["payments"]],
            client_uuid=v["client_uuid"],
            notes=v.get("notes"),
            request=request,
        )
        return Response(
            InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def hold(self, request, pk=None):
        invoice = self.get_object()
        body = HoldSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        holds.hold(invoice, label=body.validated_data["label"], user=request.user, request=request)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def recall(self, request, pk=None):
        invoice = self.get_object()
        holds.recall(invoice, user=request.user, request=request)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.cancel.threshold_high")])
    def cancel(self, request, pk=None):
        invoice = self.get_object()
        body = CancelSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        cancellation.cancel_invoice(
            invoice, reason=body.validated_data["reason"],
            user=request.user, request=request,
        )
        return Response(InvoiceSerializer(invoice).data)

    def _fetch_tenant_object(self, model, pk):
        try:
            return model.objects.for_tenant(self.request.tenant_id).get(pk=pk)
        except model.DoesNotExist:
            raise NotFound(f"{model.__name__} not found.")


class CashSessionViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = CashSession.objects.select_related("branch", "terminal", "cashier").all()
    permission_classes = [IsTenantMember]
    serializer_class = type(  # tiny inline serializer; nothing fancy
        "CashSessionSerializer", (object,), {},
    )

    def get_serializer_class(self):
        from rest_framework import serializers

        class _Ser(serializers.ModelSerializer):
            class Meta:
                model = CashSession
                fields = (
                    "id", "branch", "terminal", "cashier",
                    "opened_at", "opened_with_amount",
                    "closed_at", "closed_with_amount",
                    "expected_amount", "variance", "variance_reason",
                    "total_sales", "total_returns", "cash_in", "cash_out",
                    "status", "created_at", "updated_at",
                )
                read_only_fields = fields
        return _Ser

    @action(detail=False, methods=["post"], url_path="open",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def open(self, request):
        body = SessionOpenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        branch = Branch.objects.for_tenant(request.tenant_id).get(pk=v["branch"])
        terminal = Terminal.objects.for_tenant(request.tenant_id).get(pk=v["terminal"])
        session = sessions.open_session(
            tenant_id=request.tenant_id, branch=branch, terminal=terminal,
            cashier=request.user, opening_amount=v["opening_amount"],
            request=request,
        )
        return Response(self.get_serializer(session).data, status=201)

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def close(self, request, pk=None):
        session = self.get_object()
        body = SessionCloseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        sessions.close_session(
            session=session,
            declared_amount=v["declared_amount"],
            variance_reason=v.get("variance_reason", ""),
            cashier=request.user,
            request=request,
        )
        return Response(self.get_serializer(session).data)
