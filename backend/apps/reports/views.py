"""Reports API.

Endpoints:

  GET  /api/reports/                       — list registered reports
  POST /api/reports/<name>/preview/        — sync run, capped at 1000 rows
  POST /api/reports/<name>/export/         — sync export (CSV/XLSX/PDF)
                                             OR queue async if too large
  GET  /api/reports/dashboard/             — populated dashboard
  POST /api/reports/runs/                  — explicitly queue async
  GET  /api/reports/runs/                  — list this user's runs
  GET  /api/reports/runs/<id>/             — status of one run
  GET  /api/reports/runs/<id>/download/    — download a ready run
  GET  /api/reports/favorites/             — list saved filters for this user
  POST /api/reports/favorites/             — save one
  DEL  /api/reports/favorites/<id>/        — delete one
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, fields
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Sum
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class _IgnoreFormatQueryParam(DefaultContentNegotiation):
    """The export endpoint uses ?format=pdf|xlsx|csv to pick the FILE format it
    generates itself — it is NOT a DRF renderer suffix. DRF's default negotiation
    treats ?format=pdf as a request for a renderer named "pdf", finds none, and
    404s before the view body ever runs (so CSV/XLSX/PDF downloads all failed).
    Forcing the first configured renderer (JSON) regardless of the query param
    lets the view read `format` itself and return the right file. See
    ReportExportView."""

    def select_renderer(self, request, renderers, format_suffix=None):
        # Ignore any requested format suffix entirely — always use the first
        # renderer so negotiation never 404s on ?format=pdf|xlsx|csv.
        return (renderers[0], renderers[0].media_type)

from apps.accounts.permissions import HasModule
from apps.fbr.models import FbrSubmission
from apps.inventory.models import StockLevel
from apps.sales.models import Invoice, Payment

# All reports endpoints require at least the basic-reports module.
# Advanced exports / scheduled reports gate further on `reports_advanced`
# at the per-action level (see ReportExportView).
_REPORTS_BASIC_GATE = HasModule.for_module("reports_basic")
_REPORTS_ADVANCED_GATE = HasModule.for_module("reports_advanced")

from .aggregates import COUNTED_STATUSES
from .base import BaseFilters, ReportResult
from .exports import excel_response, pdf_response, streaming_csv_response
from .models import DailySalesSummary, ReportFavorite, ReportRun
from .registry import all_reports, get
from .serializers import ReportFavoriteSerializer, ReportRunSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_tenant(request) -> str:
    tenant_id = getattr(request, "tenant_id", None)
    if not tenant_id:
        raise PermissionDenied("Tenant context required.")
    return str(tenant_id)


def _build_filters(report_cls, payload: dict) -> BaseFilters:
    """Coerce a JSON dict into the report's Filters dataclass."""
    valid_keys = {f.name for f in fields(report_cls.Filters)}
    return report_cls.Filters(**{k: v for k, v in (payload or {}).items() if k in valid_keys})


def _serialize_result(result: ReportResult) -> dict:
    return {
        "columns": [
            {"key": c.key, "label": c.label, "kind": c.kind, "align": c.align}
            for c in result.columns
        ],
        "rows": [_jsonify_row(r) for r in result.rows],
        "totals": _jsonify_row(result.totals) if result.totals else {},
        "chart": (
            {"type": result.chart.type, "x_key": result.chart.x_key,
             "y_keys": list(result.chart.y_keys)}
            if result.chart else None
        ),
        "row_count": result.row_count,
        "truncated": result.truncated,
    }


def _jsonify_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _should_run_async(filters: BaseFilters) -> bool:
    if filters.date_from and filters.date_to:
        delta = (filters.date_to - filters.date_from).days
        if delta > 30:
            return True
    return False


# ---------------------------------------------------------------------------
# Registry / preview / export
# ---------------------------------------------------------------------------


class ReportRegistryView(APIView):
    permission_classes = [_REPORTS_BASIC_GATE, IsAuthenticated]

    def get(self, request):
        _require_tenant(request)
        out = []
        for name, cls in all_reports().items():
            out.append({
                "name": name,
                "columns": [
                    {"key": c.key, "label": c.label, "kind": c.kind}
                    for c in cls.columns
                ],
                "filter_fields": [f.name for f in fields(cls.Filters)],
                "chart": (
                    {"type": cls.chart_spec.type}
                    if cls.chart_spec else None
                ),
            })
        return Response({"results": out})


class ReportPreviewView(APIView):
    permission_classes = [_REPORTS_BASIC_GATE, IsAuthenticated]

    def post(self, request, name: str):
        tenant_id = _require_tenant(request)
        try:
            report_cls = get(name)
        except KeyError:
            raise NotFound(f"No report named {name!r}")
        filters = _build_filters(report_cls, request.data)
        result = report_cls(tenant_id=tenant_id, filters=filters).run()
        return Response(_serialize_result(result))


class ReportExportView(APIView):
    # Exports are advanced: PDF/Excel/CSV downloads cost more compute
    # and are typically tied to scheduled reports.
    permission_classes = [_REPORTS_ADVANCED_GATE, IsAuthenticated]
    # ?format=pdf|xlsx|csv selects the FILE format, not a DRF renderer — without
    # this, DRF 404s on the unknown format before the view runs.
    content_negotiation_class = _IgnoreFormatQueryParam

    def post(self, request, name: str):
        tenant_id = _require_tenant(request)
        try:
            report_cls = get(name)
        except KeyError:
            raise NotFound(f"No report named {name!r}")
        fmt = request.query_params.get("format", "csv").lower()
        if fmt not in ("csv", "xlsx", "pdf"):
            return Response(
                {"detail": f"Unsupported format {fmt!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filters = _build_filters(report_cls, request.data)

        if _should_run_async(filters):
            run = ReportRun.objects.create(
                tenant_id=tenant_id,
                user=request.user,
                report_name=name,
                filters_json=_serializable_filters(filters),
                export_format=fmt,
                status="queued",
            )
            from .tasks import run_async_report
            run_async_report.delay(str(run.id))
            return Response(
                ReportRunSerializer(run).data,
                status=status.HTTP_202_ACCEPTED,
            )

        result = report_cls(tenant_id=tenant_id, filters=filters).run(
            use_cache=False, cap=1_000_000,
        )
        filename = f"{name}-{timezone.now().strftime('%Y%m%d-%H%M%S')}.{fmt}"
        if fmt == "csv":
            return streaming_csv_response(result, filename=filename)
        if fmt == "xlsx":
            return excel_response(result, filename=filename, sheet_name=name)
        # pdf
        tenant = request.tenant
        return pdf_response(
            result, filename=filename, title=name.replace("_", " ").title(),
            tenant_business_name=tenant.business_name,
            tenant_ntn=tenant.ntn,
            subtitle=_filter_subtitle(filters),
        )


def _filter_subtitle(filters: BaseFilters) -> str:
    """Human-readable filter context for the PDF header (date range / branch),
    so a printed report states the period it covers."""
    parts = []
    df = getattr(filters, "date_from", None)
    dt_ = getattr(filters, "date_to", None)
    if df or dt_:
        parts.append(f"Period: {df or '…'} to {dt_ or '…'}")
    else:
        parts.append("Period: all time")
    if getattr(filters, "branch_id", None):
        parts.append(f"Branch: {filters.branch_id}")
    return "   ·   ".join(parts)


def _serializable_filters(filters: BaseFilters) -> dict:
    """asdict() but with date → isoformat for JSON-friendly storage."""
    out = {}
    for k, v in asdict(filters).items():
        if isinstance(v, dt.date):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Async runs
# ---------------------------------------------------------------------------


class ReportRunViewSet(viewsets.ModelViewSet):
    serializer_class = ReportRunSerializer
    # Async report runs (background generation, schedules) are advanced.
    permission_classes = [_REPORTS_ADVANCED_GATE, IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            ReportRun.objects.for_tenant(_require_tenant(self.request))
            .filter(user=self.request.user)
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        from .tasks import run_async_report
        instance = serializer.save(
            tenant_id=_require_tenant(self.request),
            user=self.request.user,
            status="queued",
        )
        run_async_report.delay(str(instance.id))

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        run = self.get_object()
        if run.status != "ready":
            return Response(
                {"detail": f"Run is {run.status!r}, not ready."},
                status=status.HTTP_409_CONFLICT,
            )
        full_path = Path(settings.MEDIA_ROOT) / run.output_path
        if not full_path.exists():
            raise NotFound("Output file no longer present.")
        return FileResponse(
            open(full_path, "rb"),
            as_attachment=True, filename=full_path.name,
        )


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


class ReportFavoriteViewSet(viewsets.ModelViewSet):
    # Favorites = saved configurations; basic access is enough.
    serializer_class = ReportFavoriteSerializer
    permission_classes = [_REPORTS_BASIC_GATE, IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return (
            ReportFavorite.objects.for_tenant(_require_tenant(self.request))
            .filter(user=self.request.user)
            .order_by("report_name", "label")
        )

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=_require_tenant(self.request),
            user=self.request.user,
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@api_view(["GET"])
# NOTE: dashboard is the admin web's landing page; gating it would brick
# the home screen for tenants without reports_basic. The data the
# dashboard returns (today's sales, sync health) is always-available
# context, not a real "report".
@permission_classes([IsAuthenticated])
def dashboard_view(request):
    tenant_id = _require_tenant(request)
    today = timezone.localdate()
    seven_ago = today - dt.timedelta(days=6)

    rows_7d = list(
        DailySalesSummary.objects.for_tenant(tenant_id)
        .filter(date__gte=seven_ago, date__lte=today)
        .values("date")
        .annotate(
            gross=Sum("gross"),
            invoice_count=Sum("invoice_count"),
            refund_count=Sum("refund_count"),
        )
        .order_by("date")
    )
    by_date = {r["date"]: r for r in rows_7d}

    today_row = by_date.get(today, {})
    today_gross = today_row.get("gross") or Decimal("0")
    today_count = today_row.get("invoice_count") or 0
    today_refunds = today_row.get("refund_count") or 0
    avg_ticket = (today_gross / today_count) if today_count else Decimal("0")

    sparkline = []
    for i in range(7):
        d = seven_ago + dt.timedelta(days=i)
        r = by_date.get(d, {})
        sparkline.append({
            "date": d.isoformat(),
            "gross": str(r.get("gross") or Decimal("0")),
        })

    # Recent invoices.
    recent = (
        Invoice.objects.for_tenant(tenant_id)
        .filter(status__in=COUNTED_STATUSES)
        .select_related("branch", "cashier")
        .order_by("-created_at")[:5]
    )
    recent_invoices = [
        {
            "id": str(i.id),
            "local_invoice_number": i.local_invoice_number,
            "branch": i.branch.name,
            "cashier": i.cashier.email if i.cashier_id else "",
            "grand_total": str(i.grand_total),
            "status": i.status,
            "created_at": i.created_at.isoformat(),
        }
        for i in recent
    ]

    # Low stock — explicit Python loop because mixing F() and slicing
    # with select_related is brittle, and the result set is tiny.
    low_stock = []
    for s in (
        StockLevel.objects.for_tenant(tenant_id)
        .filter(reorder_level__isnull=False)
        .select_related("product", "branch")
    ):
        if s.reorder_level is not None and s.quantity <= s.reorder_level:
            low_stock.append({
                "sku": s.product.sku,
                "name": s.product.name,
                "branch": s.branch.name,
                "quantity": str(s.quantity),
                "reorder_level": str(s.reorder_level),
            })
            if len(low_stock) >= 5:
                break

    # Failed FBR submissions.
    failed_fbr = (
        FbrSubmission.objects.for_tenant(tenant_id)
        .exclude(status_code="00")
        .select_related("invoice")
        .order_by("-submitted_at")[:5]
    )
    failed_rows = [
        {
            "id": str(f.id),
            "invoice_number": f.invoice.local_invoice_number if f.invoice else "",
            "status_code": f.status_code,
            "error": (f.error_message or "")[:120],
            "submitted_at": f.submitted_at.isoformat(),
        }
        for f in failed_fbr
    ]

    # Today's payment-method breakdown.
    pm_rows = (
        Payment.objects.for_tenant(tenant_id)
        .filter(status="completed", invoice__invoice_date=today)
        .values("payment_method")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    payment_breakdown = [
        {
            "method": r["payment_method"],
            "total": str(r["total"] or Decimal("0")),
            "count": r["count"],
        }
        for r in pm_rows
    ]

    last_built = (
        DailySalesSummary.objects.for_tenant(tenant_id)
        .order_by("-last_built_at")
        .values_list("last_built_at", flat=True)
        .first()
    )

    # ── Entity overview totals (dashboard cards) ──────────────────────────
    # Lightweight aggregate counts the dashboard cards read directly, so the
    # client doesn't fetch 4 list endpoints just for their `.count`. All
    # tenant-scoped; mode-irrelevant cards are hidden client-side.
    from decimal import Decimal as _D

    from django.db.models import DecimalField, F
    from django.db.models.functions import Coalesce

    from apps.catalog.models import Product
    from apps.customers.models import Customer
    from apps.inventory.models import Warehouse
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.only("business_mode").get(pk=tenant_id)
    month_start = today.replace(day=1)

    products_active = (
        Product.objects.for_tenant(tenant_id)
        .filter(deleted_at__isnull=True, is_active=True)
        .count()
    )
    customers_total = (
        Customer.objects.for_tenant(tenant_id).filter(deleted_at__isnull=True).count()
    )

    invoices_qs = Invoice.objects.for_tenant(tenant_id).filter(status__in=COUNTED_STATUSES)
    invoices_total = invoices_qs.count()
    month_agg = invoices_qs.filter(invoice_date__gte=month_start).aggregate(
        c=Count("id"), gross=Sum("grand_total"),
    )

    # Stock: on-hand lines, count at/below reorder, total value at cost.
    stock_qs = StockLevel.objects.for_tenant(tenant_id)
    stock_items = stock_qs.filter(quantity__gt=0).count()
    low_stock_count = stock_qs.filter(
        reorder_level__isnull=False, quantity__lte=F("reorder_level"),
    ).count()
    stock_value = stock_qs.aggregate(
        v=Coalesce(
            Sum(
                F("quantity") * F("product__cost_price"),
                output_field=DecimalField(max_digits=18, decimal_places=4),
            ),
            _D("0"),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        ),
    )["v"]

    warehouses_total = (
        Warehouse.objects.for_tenant(tenant_id).filter(deleted_at__isnull=True).count()
    )

    return Response({
        "kpis": {
            "today_gross": str(today_gross),
            "today_count": today_count,
            "today_refunds": today_refunds,
            "avg_ticket": str(avg_ticket),
        },
        "totals": {
            "business_mode": tenant.business_mode,
            "products_active": products_active,
            "customers": customers_total,
            "invoices_total": invoices_total,
            "invoices_month_count": month_agg["c"] or 0,
            "invoices_month_gross": str(month_agg["gross"] or _D("0")),
            "stock_items": stock_items,
            "low_stock_count": low_stock_count,
            "stock_value": str(stock_value or _D("0")),
            "warehouses": warehouses_total,
        },
        "sparkline": sparkline,
        "recent_invoices": recent_invoices,
        "low_stock": low_stock,
        "failed_fbr": failed_rows,
        "payment_breakdown": payment_breakdown,
        "freshness": {
            "last_built_at": last_built.isoformat() if last_built else None,
        },
    })
