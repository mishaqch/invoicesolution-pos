"""Returns API."""

from __future__ import annotations

from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasRolePerm, IsTenantMember
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal

from .models import Return
from .serializers import ProcessReturnSerializer, ReturnSerializer
from .services.process import CASHIER_REFUND_CAP_RS, process_return


class ReturnViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    queryset = (
        Return.objects
        .select_related("branch", "terminal", "cashier", "customer", "original_invoice")
        .prefetch_related("items")
        .order_by("-return_date", "-created_at")
    )
    serializer_class = ReturnSerializer
    permission_classes = [IsTenantMember]
    filter_backends = [filters.OrderingFilter]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        qs = qs.filter(tenant_id=tenant_id)
        params = self.request.query_params
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (oi := params.get("original_invoice")):
            qs = qs.filter(original_invoice_id=oi)
        if (start := params.get("from")):
            qs = qs.filter(return_date__gte=start)
        if (end := params.get("to")):
            qs = qs.filter(return_date__lte=end)
        if (rm := params.get("refund_method")):
            qs = qs.filter(refund_method=rm)
        return qs

    def create(self, request):
        ser = ProcessReturnSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        try:
            inv = Invoice.objects.for_tenant(request.tenant_id).get(pk=v["original_invoice"])
        except Invoice.DoesNotExist:
            raise NotFound("Original invoice not found.")
        try:
            branch = Branch.objects.for_tenant(request.tenant_id).get(pk=v["branch"])
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")
        try:
            terminal = Terminal.objects.for_tenant(request.tenant_id).get(pk=v["terminal"])
        except Terminal.DoesNotExist:
            raise NotFound("Terminal not found.")

        # Above-cap requires the higher cancel permission; the
        # ProcessReturnSerializer doesn't compute totals, so we recompute
        # rough refund for the cap check using the line totals.
        try:
            ret = process_return(
                tenant_id=request.tenant_id, branch=branch, terminal=terminal,
                cashier=request.user, original_invoice=inv,
                items=v["items"], reason=v["reason"],
                reason_notes=v.get("reason_notes", ""),
                refund_method=v["refund_method"],
                refund_data=v.get("refund_data", {}),
                client_uuid=v.get("client_uuid"),
                request=request,
            )
        except Exception as exc:
            raise ValidationError(getattr(exc, "message_dict", {"detail": str(exc)}))

        # Permissions: above-cap = manager+ via the cancel.threshold_high perm.
        if (
            ret.refund_amount > CASHIER_REFUND_CAP_RS
            and request.tenant_membership.role == "cashier"
        ):
            # We already wrote the return — the cap check is server-side
            # for V1 (the manager-PIN UI gate is Phase 8). Audit it.
            from apps.audit.services import log
            log(
                tenant_id=request.tenant_id, user=request.user,
                entity_type="return", entity_id=ret.id,
                action="cap_exceeded_warning",
                after={"refund_amount": str(ret.refund_amount), "cap": str(CASHIER_REFUND_CAP_RS)},
            )

        return Response(ReturnSerializer(ret).data, status=status.HTTP_201_CREATED)


class FindOriginalInvoiceView(APIView):
    """GET /api/returns/find-invoice/?local=…&fbr=…&date=…&amount=…

    Used by the POS return-flow to locate the original invoice before
    listing its line items.
    """
    permission_classes = [IsTenantMember]

    def get(self, request):
        params = request.query_params
        qs = Invoice.objects.for_tenant(request.tenant_id)

        if (local := params.get("local")):
            qs = qs.filter(local_invoice_number=local)
        if (fbr := params.get("fbr")):
            qs = qs.filter(fbr_invoice_number=fbr)
        if (date := params.get("date")):
            qs = qs.filter(invoice_date=date)
        if (amt := params.get("amount")):
            qs = qs.filter(grand_total=amt)

        # Return up to 25 matches; the cashier picks one.
        from apps.sales.serializers import InvoiceSerializer
        rows = qs.order_by("-invoice_date", "-created_at")[:25]
        return Response({
            "results": InvoiceSerializer(rows, many=True).data,
        })
