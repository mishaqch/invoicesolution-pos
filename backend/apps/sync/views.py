"""Sync API endpoints.

POS terminals POST per-entity sync rows. Server is idempotent on
client_uuid (DB UNIQUE constraint).
"""

from __future__ import annotations

from django.db.models import Max, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantMember
from apps.sales.models import Invoice
from apps.sales.serializers import InvoiceSerializer
from apps.tenants.models import Terminal

from .models import SyncLog
from .serializers import (
    IngestCustomerSerializer,
    IngestInvoiceSerializer,
    SyncLogSerializer,
    TerminalSyncStatusSerializer,
)
from .services import (
    IngestResult,
    ingest_customer,
    ingest_invoice,
    retry_failed,
)


def _resolve_terminal(request, terminal_id) -> Terminal:
    try:
        return Terminal.objects.for_tenant(request.tenant_id).get(pk=terminal_id)
    except Terminal.DoesNotExist:
        raise NotFound("Terminal not found.")


class IngestInvoiceView(APIView):
    """POST /api/sync/invoices/. Idempotent on client_uuid."""
    permission_classes = [IsTenantMember]

    def post(self, request):
        ser = IngestInvoiceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        terminal = _resolve_terminal(request, v["terminal"])

        result: IngestResult = ingest_invoice(
            tenant_id=request.tenant_id,
            terminal_id=terminal.id,
            payload=request.data,
            request=request,
        )

        if result.failed:
            return Response(
                {
                    "sync_status": "failed",
                    "sync_log_id": str(result.sync_log.id),
                    "error": result.error,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = Invoice.objects.get(pk=result.entity_id)
        body = InvoiceSerializer(invoice).data
        body["sync_status"] = "duplicate" if result.was_duplicate else "processed"
        body["sync_log_id"] = str(result.sync_log.id)
        return Response(
            body,
            status=status.HTTP_200_OK if result.was_duplicate else status.HTTP_201_CREATED,
        )


class IngestCustomerView(APIView):
    """POST /api/sync/customers/."""
    permission_classes = [IsTenantMember]

    def post(self, request):
        ser = IngestCustomerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        terminal_id = request.data.get("terminal")
        if not terminal_id:
            raise ValidationError({"terminal": "Required."})
        terminal = _resolve_terminal(request, terminal_id)

        result = ingest_customer(
            tenant_id=request.tenant_id,
            terminal_id=terminal.id,
            payload=request.data,
        )

        if result.failed:
            return Response(
                {
                    "sync_status": "failed",
                    "sync_log_id": str(result.sync_log.id),
                    "error": result.error,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "id": str(result.entity_id),
                "sync_status": "duplicate" if result.was_duplicate else "processed",
                "sync_log_id": str(result.sync_log.id),
            },
            status=status.HTTP_200_OK if result.was_duplicate else status.HTTP_201_CREATED,
        )


class SyncStatusView(APIView):
    """GET /api/sync/status/?terminal_id=...

    Returns one row per terminal (or filtered to one terminal). Used by:
      - the POS sync indicator (its own terminal)
      - the admin dashboard sync-health tile (all terminals)
    """
    permission_classes = [IsTenantMember]

    def get(self, request):
        terminal_id = request.query_params.get("terminal_id")
        terminals_qs = Terminal.objects.for_tenant(request.tenant_id).filter(is_active=True)
        if terminal_id:
            terminals_qs = terminals_qs.filter(pk=terminal_id)

        results = []
        for t in terminals_qs:
            agg = SyncLog.objects.filter(tenant_id=request.tenant_id, terminal=t).aggregate(
                pending=_count(status="received"),
                failed=_count(status="failed"),
                last_processed=Max("processed_at"),
            )
            results.append({
                "terminal": str(t.id),
                "pending": agg["pending"] or 0,
                "failed": agg["failed"] or 0,
                "last_processed_at": agg["last_processed"],
                "last_seen_at": t.last_seen_at,
            })
        return Response({
            "results": TerminalSyncStatusSerializer(results, many=True).data,
        })


class SyncLogViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    """GET /api/sync/log/?terminal_id=&status= and POST /api/sync/log/<id>/retry/."""
    queryset = SyncLog.objects.select_related("terminal").order_by("-received_at")
    serializer_class = SyncLogSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        qs = qs.filter(tenant_id=tenant_id)
        if (t := self.request.query_params.get("terminal_id")):
            qs = qs.filter(terminal_id=t)
        if (s := self.request.query_params.get("status")):
            qs = qs.filter(status=s)
        return qs

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        sync_row = self.get_object()
        try:
            result = retry_failed(sync_row, request=request)
        except Exception as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({
            "id": str(result.entity_id),
            "sync_status": "processed",
            "sync_log_id": str(result.sync_log.id),
        })


def _count(**kwargs):
    """Inline helper because Django's Count(filter=...) is more verbose."""
    from django.db.models import Count, Q
    return Count("id", filter=Q(**kwargs))
