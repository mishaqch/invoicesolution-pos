"""Customers API."""

from __future__ import annotations

from rest_framework import filters, mixins, viewsets

from apps.accounts.permissions import HasModule, HasRolePerm, IsTenantMember

_CUSTOMERS_GATE = HasModule.for_module("customers")

from .models import Customer, CustomerGroup, CustomerLedger
from .serializers import (
    CustomerGroupSerializer,
    CustomerLedgerSerializer,
    CustomerSerializer,
)


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class CustomerGroupViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = CustomerGroup.objects.all().order_by("name")
    serializer_class = CustomerGroupSerializer
    permission_classes = [
        _CUSTOMERS_GATE,
        HasRolePerm.with_perm("settings.business_profile"),
    ]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class CustomerViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.filter(deleted_at__isnull=True).order_by("name")
    serializer_class = CustomerSerializer
    permission_classes = [_CUSTOMERS_GATE, IsTenantMember]   # cashier needs read
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "phone", "cnic", "ntn"]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        from django.utils import timezone
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


class CustomerLedgerViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet,
):
    queryset = CustomerLedger.objects.select_related("customer").order_by("-created_at")
    serializer_class = CustomerLedgerSerializer
    permission_classes = [_CUSTOMERS_GATE, IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        if (c := self.request.query_params.get("customer")):
            qs = qs.filter(customer_id=c)
        return qs
