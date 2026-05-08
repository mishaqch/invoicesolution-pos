"""FBR API endpoints — A12 wizard + scenarios + submissions + budget."""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasRolePerm, IsTenantMember
from apps.sales.models import Invoice
from apps.tenants.models import Tenant
from django.utils import timezone

from .budget import current_month_start_pkt, recompute_monthly_budget
from .models import (
    FbrCancelBudget,
    FbrIpWhitelist,
    FbrScenarioTest,
    FbrSubmission,
    FbrToken,
)
from .scenarios import eligible_scenarios
from .serializers import (
    CancelInvoiceSerializer,
    FbrCancelBudgetSerializer,
    FbrIpWhitelistSerializer,
    FbrScenarioTestSerializer,
    FbrSubmissionSerializer,
    FbrTokenSerializer,
    TokenSubmitSerializer,
)
from .services import (
    activate_production_token,
    all_scenarios_passed,
    cancel_invoice_with_fbr,
    run_scenarios,
)
from .tasks import submit_invoice_to_fbr


class _TenantQuerySetMixin:
    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Status / dashboard
# ---------------------------------------------------------------------------


class FbrStatusView(APIView):
    """GET /api/fbr/status/

    Returns a single dict for the active tenant: token presence, last
    successful submission, eligible scenarios + how many have passed.
    """
    permission_classes = [IsTenantMember]

    def get(self, request):
        tenant_id = request.tenant_id
        sandbox = FbrToken.objects.filter(tenant_id=tenant_id, environment="sandbox").first()
        production = FbrToken.objects.filter(tenant_id=tenant_id, environment="production").first()

        last_success = (
            FbrSubmission.objects.filter(tenant_id=tenant_id, status_code="00")
            .order_by("-submitted_at").first()
        )

        tenant = Tenant.objects.get(pk=tenant_id)
        eligible = [
            {"code": m.code, "description": m.description}
            for m in eligible_scenarios(tenant)
        ]
        passed = (
            FbrScenarioTest.objects.filter(tenant_id=tenant_id, status="success")
            .values_list("scenario_code", flat=True)
        )

        return Response({
            "tenant_id": str(tenant_id),
            "environment": (
                "production" if production and production.is_active
                else "sandbox" if sandbox and sandbox.is_active
                else "none"
            ),
            "sandbox": FbrTokenSerializer(sandbox).data if sandbox else None,
            "production": FbrTokenSerializer(production).data if production else None,
            "last_successful_submission_at": last_success.submitted_at if last_success else None,
            "eligible_scenarios": eligible,
            "passed_scenarios": list(passed),
            "all_scenarios_passed": all_scenarios_passed(tenant),
        })


# ---------------------------------------------------------------------------
# Tokens — sandbox / production
# ---------------------------------------------------------------------------


class SubmitSandboxTokenView(APIView):
    permission_classes = [HasRolePerm.with_perm("fbr.tokens.manage")]

    def post(self, request):
        ser = TokenSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        obj, _ = FbrToken.objects.update_or_create(
            tenant_id=request.tenant_id, environment="sandbox",
            defaults={
                "api_endpoint": v["api_endpoint"],
                "is_active": True,
                "activated_at": timezone.now(),
            },
        )
        obj.set_token(v["token"])
        obj.save(update_fields=["token_encrypted", "updated_at"])
        return Response(FbrTokenSerializer(obj).data, status=201)


class ActivateProductionTokenView(APIView):
    permission_classes = [HasRolePerm.with_perm("fbr.tokens.manage")]

    def post(self, request):
        ser = TokenSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        tenant = Tenant.objects.get(pk=request.tenant_id)
        try:
            obj = activate_production_token(
                tenant=tenant, token=v["token"], api_endpoint=v["api_endpoint"],
            )
        except ValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(FbrTokenSerializer(obj).data, status=201)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class ScenarioTestViewSet(_TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = FbrScenarioTest.objects.order_by("scenario_code")
    serializer_class = FbrScenarioTestSerializer
    permission_classes = [IsTenantMember]

    @action(detail=False, methods=["post"], url_path="run-all",
            permission_classes=[HasRolePerm.with_perm("fbr.tokens.manage")])
    def run_all(self, request):
        tenant = Tenant.objects.get(pk=request.tenant_id)
        try:
            results = run_scenarios(tenant)
        except ValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"results": results})


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


class SubmissionViewSet(_TenantQuerySetMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = FbrSubmission.objects.select_related("invoice").order_by("-submitted_at")
    serializer_class = FbrSubmissionSerializer
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        if (inv := self.request.query_params.get("invoice")):
            qs = qs.filter(invoice_id=inv)
        if (s := self.request.query_params.get("status_code")):
            qs = qs.filter(status_code=s)
        return qs

    @action(detail=False, methods=["post"], url_path="retry/(?P<invoice_id>[^/.]+)",
            permission_classes=[HasRolePerm.with_perm("fbr.tokens.manage")])
    def retry(self, request, invoice_id=None):
        try:
            invoice = Invoice.objects.for_tenant(request.tenant_id).get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")
        # If the task is already running we'd dedupe via Celery's idempotency
        # in real prod; for V1, just kick another submission.
        submit_invoice_to_fbr.delay(str(invoice.id))
        return Response({"queued": True})


# ---------------------------------------------------------------------------
# Cancel budget
# ---------------------------------------------------------------------------


class CancelBudgetView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        tenant = Tenant.objects.get(pk=request.tenant_id)
        budget = (
            FbrCancelBudget.objects.filter(
                tenant=tenant, month_start=current_month_start_pkt(),
            )
            .prefetch_related("consumptions")
            .first()
        )
        if budget is None:
            # Create on the fly so the dashboard always has a row.
            budget = recompute_monthly_budget(tenant)
            budget.refresh_from_db()
        return Response(FbrCancelBudgetSerializer(budget).data)


# ---------------------------------------------------------------------------
# IP whitelist
# ---------------------------------------------------------------------------


class FbrIpWhitelistViewSet(viewsets.ModelViewSet):
    queryset = FbrIpWhitelist.objects.order_by("-created_at")
    serializer_class = FbrIpWhitelistSerializer
    permission_classes = [HasRolePerm.with_perm("fbr.tokens.manage")]

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        # Show this tenant's rows + global infra rows (tenant=NULL).
        if tenant_id is None:
            return qs.filter(tenant__isnull=True)
        from django.db.models import Q
        return qs.filter(Q(tenant_id=tenant_id) | Q(tenant__isnull=True))

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


# ---------------------------------------------------------------------------
# Cancel an invoice via FBR (admin-driven; respects 72h + 10% budget)
# ---------------------------------------------------------------------------


class CancelInvoiceFbrView(APIView):
    permission_classes = [HasRolePerm.with_perm("sales.cancel.threshold_high")]

    def post(self, request, invoice_id):
        try:
            invoice = Invoice.objects.for_tenant(request.tenant_id).get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFound("Invoice not found.")

        ser = CancelInvoiceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            cancel_invoice_with_fbr(
                invoice, reason=ser.validated_data["reason"],
                user=request.user, request=request,
            )
        except ValidationError as exc:
            raise ValidationError(getattr(exc, "message_dict", {"detail": str(exc)}))
        return Response({"id": str(invoice.id), "status": invoice.status})
