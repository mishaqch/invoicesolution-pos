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
    AddRoomSerializer,
    CancelStaySerializer,
    CheckoutSerializer,
    FolioListSerializer,
    OpenStaySerializer,
    RoomSerializer,
    UpdateStaySerializer,
)

# Cancelling / removing a whole stay is higher-impact than editing details,
# so gate it behind the manager/owner cancel permission (same as high-value
# invoice cancels). Editing guest details stays open to any cashier.
_CANCEL_PERM = "sales.cancel.threshold_high"

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

    def get_permissions(self):
        # Cancelling a WHOLE stay is manager/owner-only (highest impact). Adding
        # AND removing individual rooms is open to any cashier while the stay is
        # OPEN — front-desk staff routinely adjust rooms during a stay (removing
        # a room voids only that room's charges, and the folio isn't checked out
        # yet). The remove_room service still refuses once the stay is closed.
        if self.action == "cancel":
            return [_HOTEL_GATE(), HasRolePerm.with_perm(_CANCEL_PERM)()]
        return super().get_permissions()

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

        # Resolve one or many rooms (multi-room booking under one guest).
        room_ids = v.get("rooms") or ([v["room"]] if v.get("room") else [])
        found = {
            str(r.id): r for r in Room.objects.for_tenant(request.tenant_id)
            .filter(pk__in=room_ids, deleted_at__isnull=True)
        }
        rooms = [found[str(rid)] for rid in room_ids if str(rid) in found]
        if len(rooms) != len(room_ids):
            raise NotFound("One or more rooms not found.")

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
                rooms=[{"room": r} for r in rooms],
                check_in=v.get("check_in"),
                expected_check_out=v.get("expected_check_out"),
                guest_email=v.get("guest_email", ""),
                guest_address=v.get("guest_address", ""),
                partner_name=v.get("partner_name", ""),
                partner_cnic=v.get("partner_cnic", ""),
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
        room = None
        if v.get("room"):
            room = Room.objects.for_tenant(request.tenant_id).filter(pk=v["room"]).first()
            if room is None:
                raise NotFound("Room not found.")
        try:
            services.add_charge(
                folio=folio,
                terminal=terminal,
                cashier=request.user,
                cash_session=cash_session,
                cart_lines=v["cart_lines"],
                kind=v.get("kind", "restaurant"),
                charge_date=v.get("charge_date"),
                room=room,
                client_uuid=v.get("client_uuid"),
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"charges/(?P<charge_id>[^/.]+)")
    def remove_charge(self, request, pk=None, charge_id=None):
        """Void an entire charge entry on an open folio (audit-kept)."""
        folio = self._get_folio(request, pk)
        charge = self._get_charge(folio, charge_id)
        try:
            services.void_charge(folio=folio, charge=charge, user=request.user)
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio))

    @action(detail=True, methods=["delete"],
            url_path=r"charges/(?P<charge_id>[^/.]+)/items/(?P<item_id>[^/.]+)")
    def remove_item(self, request, pk=None, charge_id=None, item_id=None):
        """Void one item on a charge (open folio only). Bill total drops."""
        folio = self._get_folio(request, pk)
        charge = self._get_charge(folio, charge_id)
        try:
            services.void_item(
                folio=folio, charge=charge, sale_item_id=item_id, user=request.user,
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio))

    def _get_charge(self, folio, charge_id):
        from .models import FolioInvoice
        charge = (
            FolioInvoice.objects.for_tenant(folio.tenant_id)
            .filter(pk=charge_id, folio=folio).select_related("invoice").first()
        )
        if charge is None:
            raise NotFound("Charge not found.")
        return charge

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

    def partial_update(self, request, pk=None):
        """Edit an open stay's guest details and/or dates."""
        folio = self._get_folio(request, pk)
        ser = UpdateStaySerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        dates_changed = "check_in" in v or "expected_check_out" in v
        terminal = cash_session = None
        if dates_changed:
            _, terminal, cash_session = _resolve_context(request, v.get("terminal"))
        try:
            folio = services.update_stay(
                folio=folio,
                fields={
                    k: v[k] for k in (
                        "guest_name", "guest_cnic", "guest_phone",
                        "guest_email", "guest_address",
                        "partner_name", "partner_cnic", "notes",
                    ) if k in v
                },
                check_in=v.get("check_in") if dates_changed else None,
                expected_check_out=v.get("expected_check_out") if dates_changed else None,
                terminal=terminal,
                cashier=request.user,
                cash_session=cash_session,
                user=request.user,
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio))

    @action(detail=True, methods=["post"])
    def rooms(self, request, pk=None):
        """Add a room to an open stay (same guest)."""
        folio = self._get_folio(request, pk)
        ser = AddRoomSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        room = Room.objects.for_tenant(request.tenant_id).filter(
            pk=v["room"], deleted_at__isnull=True,
        ).first()
        if room is None:
            raise NotFound("Room not found.")
        _, terminal, cash_session = _resolve_context(request, v.get("terminal"))
        try:
            folio = services.add_room_to_stay(
                folio=folio, room=room, terminal=terminal,
                cashier=request.user, cash_session=cash_session,
                check_in=v.get("check_in"),
                expected_check_out=v.get("expected_check_out"),
                user=request.user,
            )
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"rooms/(?P<room_id>[^/.]+)")
    def remove_room(self, request, pk=None, room_id=None):
        """Remove a room from an open multi-room stay (manager/owner only)."""
        folio = self._get_folio(request, pk)
        room = Room.objects.for_tenant(request.tenant_id).filter(pk=room_id).first()
        if room is None:
            raise NotFound("Room not found.")
        try:
            folio = services.remove_room_from_stay(folio=folio, room=room, user=request.user)
        except DjangoValidationError as e:
            raise ValidationError(getattr(e, "message_dict", {"detail": e.messages}))
        return Response(services.consolidated_bill(folio))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel an open stay — void charges (audit-kept), free rooms
        (manager/owner only)."""
        folio = self._get_folio(request, pk)
        ser = CancelStaySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            folio = services.cancel_stay(
                folio=folio, reason=ser.validated_data.get("reason", ""),
                user=request.user,
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
