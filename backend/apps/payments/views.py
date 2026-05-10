"""Payments API endpoints — Phase 5."""

from __future__ import annotations

from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasModule, HasRolePerm, IsTenantMember
from apps.sales.models import Payment
from apps.tenants.models import TenantSettings

# Cheque-tracking is the "advanced" payments feature; cash + card method
# config stays always-on so even tenants without payments_advanced can
# operate. The settings page that lists all available methods stays
# always-on too — it's a config surface, not an operational endpoint.
_ADVANCED_PAY_GATE = HasModule.for_module("payments_advanced")

from .adapters import all_methods
from .serializers import (
    ChequeBouncedSerializer,
    PaymentMethodConfigSerializer,
    PaymentSerializer,
    TenantSettingsSerializer,
)
from .services import mark_cheque_bounced, mark_cheque_cleared


def _get_settings(tenant_id) -> TenantSettings:
    obj, _ = TenantSettings.objects.get_or_create(
        tenant_id=tenant_id,
        defaults={"enabled_payment_methods": ["cash"]},
    )
    return obj


class PaymentMethodsView(APIView):
    """GET /api/payments/methods/

    Returns the per-tenant payment-method configuration that the POS needs
    to render the payment screen.
    """
    permission_classes = [IsTenantMember]

    def get(self, request):
        settings = _get_settings(request.tenant_id)
        return Response(PaymentMethodConfigSerializer(settings).data)


class PaymentSettingsView(APIView):
    """GET / PATCH /api/payments/settings/ — admin-only."""
    permission_classes = [HasRolePerm.with_perm("settings.business_profile")]

    def get(self, request):
        settings = _get_settings(request.tenant_id)
        return Response(TenantSettingsSerializer(settings).data)

    def patch(self, request):
        settings = _get_settings(request.tenant_id)
        ser = TenantSettingsSerializer(settings, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        # Validate enabled_payment_methods values.
        enabled = ser.validated_data.get("enabled_payment_methods")
        if enabled is not None:
            allowed = set(all_methods())
            unknown = set(enabled) - allowed
            if unknown:
                raise ValidationError({
                    "enabled_payment_methods": f"Unknown method(s): {sorted(unknown)}",
                })
        ser.save()
        return Response(ser.data)


class ChequeViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    """Pending / cleared / bounced cheques. Admin view."""

    queryset = Payment.objects.filter(payment_method="cheque").order_by("-created_at")
    serializer_class = PaymentSerializer
    permission_classes = [_ADVANCED_PAY_GATE, HasRolePerm.with_perm("inventory.adjust")]
    filter_backends = [filters.OrderingFilter]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        qs = qs.filter(tenant_id=tenant_id)
        if (s := self.request.query_params.get("status")):
            qs = qs.filter(cheque_status=s)
        return qs

    @action(detail=True, methods=["post"])
    def clear(self, request, pk=None):
        payment = self.get_object()
        try:
            mark_cheque_cleared(payment, user=request.user, request=request)
        except Exception as exc:
            raise ValidationError(getattr(exc, "message_dict", {"detail": str(exc)}))
        return Response(PaymentSerializer(payment).data)

    @action(detail=True, methods=["post"])
    def bounce(self, request, pk=None):
        payment = self.get_object()
        ser = ChequeBouncedSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            mark_cheque_bounced(
                payment, reason=ser.validated_data.get("reason", ""),
                user=request.user, request=request,
            )
        except Exception as exc:
            raise ValidationError(getattr(exc, "message_dict", {"detail": str(exc)}))
        return Response(PaymentSerializer(payment).data)
