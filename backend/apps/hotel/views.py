"""Hotel API — rooms + guest folios. Gated on the `hotel` module."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import HasModule, HasRolePerm, IsTenantMember
from apps.tenants.models import Branch, CashSession, Terminal

from . import services
from .models import GuestFolio, Room
from .serializers import (
    AddChargeSerializer,
    CheckoutSerializer,
    FolioListSerializer,
    OpenStaySerializer,
    RoomSerializer,
)

_HOTEL_GATE = HasModule.for_module("hotel")


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        return qs.filter(tenant_id=tenant_id) if tenant_id else qs.none()


def _resolve_context(request, terminal_id=None):
    """Resolve (branch, terminal, cash_session) for a folio operation.

    Mirrors the manual-invoice/POS resolution: explicit terminal if supplied,
    else the tenant's implicit default pair. The open cash session for that
    terminal (if any) is attached so room/charge invoices belong to the till.
    """
    from apps.tenants.implicit import ensure_implicit_branch_and_terminal
    from apps.tenants.models import Tenant

    if terminal_id:
        terminal = (
            Terminal.objects.for_tenant(request.tenant_id).filter(pk=terminal_id).first()
        )
        if terminal is None:
            raise NotFound("Terminal not found.")
        branch = terminal.branch
    else:
        tenant = Tenant.objects.get(pk=request.tenant_id)
        branch, terminal = ensure_implicit_branch_and_terminal(tenant)

    cash_session = (
        CashSession.objects.for_tenant(request.tenant_id)
        .filter(terminal=terminal, closed_at__isnull=True)
        .order_by("-opened_at")
        .first()
    )
    return branch, terminal, cash_session


class RoomViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    """Manage bookable rooms + see availability."""

    queryset = Room.objects.filter(deleted_at__isnull=True).select_related("branch")
    serializer_class = RoomSerializer
    permission_classes = [_HOTEL_GATE, IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (s := params.get("status")):
            qs = qs.filter(status=s)
        return qs

    def get_permissions(self):
        # Reads open to any member; writes need the inventory/admin perm.
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [_HOTEL_GATE(), HasRolePerm.with_perm("inventory.adjust")()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        from django.utils import timezone
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


class FolioViewSet(_TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Guest folios — open a stay, add charges, checkout, consolidated bill."""

    queryset = GuestFolio.objects.select_related("room", "branch").all()
    serializer_class = FolioListSerializer
    permission_classes = [_HOTEL_GATE, IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (s := params.get("status")):
            qs = qs.filter(status=s)
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        return qs

    def create(self, request):
        """Open a stay."""
        ser = OpenStaySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        room = (
            Room.objects.for_tenant(request.tenant_id)
            .filter(pk=v["room"], deleted_at__isnull=True)
            .first()
        )
        if room is None:
            raise NotFound("Room not found.")

        branch, terminal, cash_session = _resolve_context(request, v.get("terminal"))
        try:
            folio = services.open_stay(
                tenant_id=request.tenant_id,
                branch=branch,
                terminal=terminal,
                cashier=request.user,
                cash_session=cash_session,
                guest_name=v["guest_name"],
                guest_cnic=v["guest_cnic"],
                guest_phone=v["guest_phone"],
                room=room,
                check_in=v.get("check_in"),
                expected_check_out=v.get("expected_check_out"),
                guest_email=v.get("guest_email", ""),
                guest_address=v.get("guest_address", ""),
                notes=v.get("notes", ""),
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))

        return Response(
            services.consolidated_bill(folio), status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        folio = self._get_folio(request, pk)
        return Response(services.consolidated_bill(folio))

    @action(detail=True, methods=["post"])
    def charges(self, request, pk=None):
        folio = self._get_folio(request, pk)
        ser = AddChargeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        branch, terminal, cash_session = _resolve_context(request, v.get("terminal"))
        try:
            services.add_charge(
                folio=folio,
                terminal=terminal,
                cashier=request.user,
                cash_session=cash_session,
                cart_lines=v["cart_lines"],
                kind=v.get("kind", "restaurant"),
                charge_date=v.get("charge_date"),
                client_uuid=v.get("client_uuid"),
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def checkout(self, request, pk=None):
        folio = self._get_folio(request, pk)
        ser = CheckoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        try:
            folio = services.checkout_stay(
                folio=folio,
                payments=v.get("payments", []),
                cashier=request.user,
                check_out=v.get("check_out"),
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio))

    def _get_folio(self, request, pk) -> GuestFolio:
        folio = (
            GuestFolio.objects.for_tenant(request.tenant_id)
            .filter(pk=pk).select_related("room", "branch").first()
        )
        if folio is None:
            raise NotFound("Folio not found.")
        return folio
