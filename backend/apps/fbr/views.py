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
from django.db.models import Max
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
    BranchFbrTokenSerializer,
    BranchTokenSubmitSerializer,
    CancelInvoiceSerializer,
    FbrCancelBudgetSerializer,
    FbrIpWhitelistSerializer,
    FbrScenarioTestSerializer,
    FbrSubmissionSerializer,
    FbrTokenSerializer,
    TokenSubmitSerializer,
)
from .services import (
    activate_branch_token,
    activate_production_token,
    all_scenarios_passed,
    cancel_invoice_with_fbr,
    deactivate_branch_token,
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
        # Two views of "which scenarios apply":
        #   - eligible_scenarios = subset with a working payload-builder
        #     (used by the runner + the all-passed gate)
        #   - assigned_scenario_codes = the full set IRIS assigned (used
        #     by the UI grid so unbuilt scenarios still appear with a
        #     "Not yet supported" pill instead of disappearing silently)
        from .scenarios import (
            assigned_scenario_codes, builder_available, scenario_description,
        )
        assigned = [
            {
                "code": code,
                "description": scenario_description(code),
                "builder_available": builder_available(code),
            }
            for code in assigned_scenario_codes(tenant)
        ]
        eligible = [s for s in assigned if s["builder_available"]]
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
            "assigned_scenarios": assigned,
            "passed_scenarios": list(passed),
            "all_scenarios_passed": all_scenarios_passed(tenant),
        })


class PosConnectionStatusView(APIView):
    """GET /api/fbr/pos-status/

    Per-branch FBR POS connection status for the active tenant. Read-only;
    purely derived from existing data, so it never touches the Digital
    Invoicing submission path.

    For each branch we report:
      - the FBR-issued POS ID + Code stored on the branch (if any),
      - whether the tenant has an active production/sandbox token (the thing
        that actually authenticates submissions to PRAL),
      - a `connected` flag + `last_validated_at`, derived from whether the
        branch has ever had an invoice validated by FBR (status=valid with an
        FBR invoice number). This mirrors the Connected/Disconnected state the
        FBR portal shows: a POS is "Connected" once it has successfully
        transmitted at least one invoice.
    """
    permission_classes = [IsTenantMember]

    def get(self, request):
        from apps.tenants.models import Branch

        from .models import BranchFbrToken

        tenant_id = request.tenant_id
        prod = FbrToken.objects.filter(
            tenant_id=tenant_id, environment="production", is_active=True,
        ).first()
        sandbox = FbrToken.objects.filter(
            tenant_id=tenant_id, environment="sandbox", is_active=True,
        ).first()
        active_token = prod or sandbox
        token_environment = (
            "production" if prod else "sandbox" if sandbox else "none"
        )

        branches = list(
            Branch.objects.filter(tenant_id=tenant_id, deleted_at__isnull=True)
            .order_by("name")
        )

        # Latest FBR-validated invoice per branch, in one query.
        validated = (
            Invoice.objects.filter(
                tenant_id=tenant_id,
                status="valid",
                fbr_invoice_number__isnull=False,
            )
            .values("branch_id")
            .annotate(last_validated_at=Max("fbr_validated_at"))
        )
        last_by_branch = {
            row["branch_id"]: row["last_validated_at"] for row in validated
        }

        # Per-branch POS token state (POS path). One query.
        branch_tokens = {
            t.branch_id: t
            for t in BranchFbrToken.objects.filter(tenant_id=tenant_id)
        }

        items = []
        for b in branches:
            last = last_by_branch.get(b.id)
            registered = bool(b.fbr_pos_id)
            bt = branch_tokens.get(b.id)
            items.append({
                "branch_id": str(b.id),
                "branch_name": b.name,
                "branch_code": b.code,
                "fbr_pos_id": b.fbr_pos_id or None,
                "fbr_pos_code": b.fbr_pos_code or None,
                "registered": registered,
                "connected": bool(last),
                "last_validated_at": last,
                # Per-branch POS token: whether a token is on file + active.
                "has_branch_token": bt is not None and bool(bt.token_encrypted),
                "branch_token_active": bool(bt.is_active) if bt else False,
            })

        return Response({
            "tenant_id": str(tenant_id),
            "token_present": active_token is not None,
            "token_environment": token_environment,
            "branches": items,
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
        # Normalise the endpoint so a pasted submission URL (with the
        # full /di_data/v1/di/postinvoicedata_sb path) doesn't get
        # persisted verbatim — the FbrClient appends those paths
        # itself at submission time.
        endpoint_base = _normalise_pral_base(v["api_endpoint"])
        new_token = (v.get("token") or "").strip()

        existing = FbrToken.objects.filter(
            tenant_id=request.tenant_id, environment="sandbox",
        ).first()

        # Empty token + no existing row = nothing to save against.
        # Send a clear 400 so the wizard surfaces it cleanly.
        if not new_token and existing is None:
            return Response(
                {"detail": "Token is required when creating a sandbox "
                 "configuration. Paste the bearer PRAL issued."},
                status=400,
            )

        obj, _ = FbrToken.objects.update_or_create(
            tenant_id=request.tenant_id, environment="sandbox",
            defaults={
                "api_endpoint": endpoint_base,
                "is_active": True,
                "activated_at": timezone.now(),
            },
        )
        # Only overwrite the encrypted token when a new value was
        # supplied. Empty token = endpoint-only update, keep the
        # existing bearer in place.
        if new_token:
            obj.set_token(new_token)
            obj.save(update_fields=["token_encrypted", "updated_at"])
        return Response(FbrTokenSerializer(obj).data, status=201)


class ActivateProductionTokenView(APIView):
    permission_classes = [HasRolePerm.with_perm("fbr.tokens.manage")]

    def post(self, request):
        ser = TokenSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        tenant = Tenant.objects.get(pk=request.tenant_id)
        # Same normalisation as sandbox — see comment in
        # SubmitSandboxTokenView.
        endpoint_base = _normalise_pral_base(v["api_endpoint"])
        # POS fiscalization tenants (pra_cloud / ims_sdc) have NO sandbox
        # scenarios at all — the tax authority issues the production token
        # directly. So the scenario gate simply doesn't apply to them and the
        # bypass is automatic (not a security override).
        #
        # For DI-API tenants the bypass IS a compliance override (activate a
        # token FBR already issued after sandbox testing on its own portal), so
        # it stays platform-staff-only; a tenant passing the flag is ignored.
        conn = getattr(tenant, "fbr_connection_type", "di_api")
        is_pos_fiscalization = conn in ("pra_cloud", "ims_sdc")
        is_platform = bool(
            getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_platform_staff", False)
        )
        bypass = is_pos_fiscalization or (
            bool(v.get("scenarios_cleared_externally")) and is_platform
        )
        try:
            obj = activate_production_token(
                tenant=tenant, token=v["token"], api_endpoint=endpoint_base,
                scenarios_cleared_externally=bypass,
            )
        except ValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(FbrTokenSerializer(obj).data, status=201)


class BranchTokenView(APIView):
    """Per-branch FBR POS token management.

    POST   /api/fbr/branch-token/  — set/update a branch's POS token.
    DELETE /api/fbr/branch-token/?branch_id=<uuid>  — deactivate it.

    POS registrations get a production token directly from FBR (no sandbox /
    scenario testing), so there's no scenario gate here. The branch must
    belong to the active tenant. Digital Invoicing is unaffected — it uses
    the tenant-level token, not this.
    """
    permission_classes = [HasRolePerm.with_perm("fbr.tokens.manage")]

    def post(self, request):
        from apps.tenants.models import Branch

        ser = BranchTokenSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        try:
            branch = Branch.objects.get(
                pk=v["branch_id"], tenant_id=request.tenant_id,
                deleted_at__isnull=True,
            )
        except Branch.DoesNotExist:
            raise NotFound("Branch not found for this tenant.")
        endpoint_base = _normalise_pral_base(v["api_endpoint"])
        try:
            obj = activate_branch_token(
                branch=branch, token=v.get("token") or "",
                api_endpoint=endpoint_base,
            )
        except ValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(BranchFbrTokenSerializer(obj).data, status=201)

    def delete(self, request):
        from apps.tenants.models import Branch

        branch_id = request.query_params.get("branch_id")
        if not branch_id:
            raise ValidationError({"detail": "branch_id query param required."})
        try:
            branch = Branch.objects.get(
                pk=branch_id, tenant_id=request.tenant_id,
                deleted_at__isnull=True,
            )
        except (Branch.DoesNotExist, ValueError):
            raise NotFound("Branch not found for this tenant.")
        changed = deactivate_branch_token(branch=branch)
        return Response({"deactivated": changed}, status=200)


def _normalise_pral_base(raw: str) -> str:
    """Coerce whatever the operator pasted into the PRAL gateway ROOT
    (scheme://host[:port]).

    Operators routinely paste the full submission URL ('.../di_data/
    v1/di/postinvoicedata_sb') into the "endpoint" field thinking
    that's what's wanted. Our client wants only the gateway root —
    it appends '/di_data/v1/di/<endpoint>_sb' itself. Stripping any
    extra path here means a paste error doesn't turn into a 404 or
    DNS-shaped failure downstream.

    Examples (all normalise to 'https://gw.fbr.gov.pk'):
      'https://gw.fbr.gov.pk'
      'https://gw.fbr.gov.pk/'
      'https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb'
      'gw.fbr.gov.pk'
      '  https://gw.fbr.gov.pk  '
    """
    from urllib.parse import urlparse, urlunparse

    cleaned = (raw or "").strip()
    if not cleaned:
        return "https://gw.fbr.gov.pk"
    # Add scheme if missing — urlparse treats a bare host as path otherwise.
    if "://" not in cleaned:
        cleaned = "https://" + cleaned
    parsed = urlparse(cleaned)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    if not netloc:
        # urlparse occasionally drops to path when given oddly-shaped
        # input; treat the raw path as the host.
        netloc = (parsed.path.split("/", 1)[0]) or "gw.fbr.gov.pk"
    return urlunparse((scheme, netloc, "", "", "", ""))


class TestTokenView(APIView):
    """Probe a PRAL token + endpoint pair WITHOUT persisting anything.

    Hits a cheap PRAL reference endpoint (/pdi/v1/uom) with the
    candidate Authorization bearer. PRAL's reference endpoints are
    fast (<300ms) and require auth, so they're the right "is this
    token usable?" probe.

    Returns:
      200 + {"ok": true, "uom_count": N}  on success
      400 + {"ok": false, "detail": "..."} on bad token / bad URL
    """
    permission_classes = [HasRolePerm.with_perm("fbr.tokens.manage")]

    def post(self, request):
        ser = TokenSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        # Normalise whatever the operator pasted — they often include
        # the full submission path which would yield a 404 if we
        # blindly appended /pdi/v1/uom to it.
        endpoint_base = _normalise_pral_base(v["api_endpoint"])
        token = v["token"]

        import requests
        url = f"{endpoint_base}/pdi/v1/uom"
        try:
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except requests.RequestException as exc:
            return Response(
                {"ok": False, "detail": f"Could not reach PRAL: {exc}"},
                status=200,  # 200 so the frontend reads body uniformly
            )

        if r.status_code == 401:
            return Response(
                {"ok": False, "detail": "PRAL rejected the token (HTTP 401). "
                 "Check the token and try again."},
                status=200,
            )
        if r.status_code == 404:
            return Response(
                {"ok": False, "detail": "PRAL returned 404 — the API endpoint "
                 "URL is probably wrong. Use https://gw.fbr.gov.pk."},
                status=200,
            )
        if r.status_code == 403 or "900908" in (r.text or ""):
            # Gateway access-control rejection — NOT a bad token (that's 401).
            # PRAL is refusing this request's ORIGIN. Almost always: the call
            # came from a machine whose IP isn't authorised — e.g. a local/dev
            # backend instead of the production server. POS sales must be
            # submitted from the server FBR recognises; test from there.
            return Response(
                {"ok": False, "detail": (
                    "PRAL returned 403 (errorCode 900908, 'Resource forbidden'). "
                    "This is an ORIGIN/access rejection, not a bad token. Run "
                    "this test from the production server that submits to FBR — "
                    "a local/dev machine will be refused. If you're already on "
                    "that server, confirm its outbound IP is the one FBR "
                    "authorised for this taxpayer."
                )},
                status=200,
            )
        if not r.ok:
            return Response(
                {"ok": False, "detail": f"PRAL returned HTTP {r.status_code}: "
                 f"{r.text[:200]}"},
                status=200,
            )

        try:
            body = r.json()
        except ValueError:
            return Response(
                {"ok": False, "detail": "PRAL returned a non-JSON response. "
                 "Endpoint may be a captive portal or proxy."},
                status=200,
            )
        if not isinstance(body, list):
            return Response(
                {"ok": False, "detail": "Unexpected response shape from PRAL."},
                status=200,
            )

        return Response({
            "ok": True,
            "uom_count": len(body),
            "endpoint_base": endpoint_base,
        })


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

    @action(detail=False, methods=["post"], url_path=r"(?P<code>SN\d{3})/run",
            permission_classes=[HasRolePerm.with_perm("fbr.tokens.manage")])
    def run_one(self, request, code: str):
        """POST /api/fbr/scenarios/<SN001|SN002|...>/run/

        Body (optional):
          { "payload": { ...full PRAL request JSON... } }

        - No body / empty body: run the builder-generated payload.
        - With `payload`: send that JSON verbatim (one-off override —
          the operator hand-edited the request on the UI and clicked
          Send). The override is NOT persisted; the next regular Run
          uses the builder again.

        Useful for iterating on a failing scenario without re-running
        the whole batch.
        """
        from .services import run_single_scenario
        tenant = Tenant.objects.get(pk=request.tenant_id)
        code = code.upper()

        # Pull optional payload override out of the body. Reject non-
        # dict overrides (PRAL won't accept anything else).
        payload_override = request.data.get("payload") if hasattr(
            request, "data"
        ) and isinstance(request.data, dict) else None
        if payload_override is not None and not isinstance(payload_override, dict):
            return Response(
                {"detail": "`payload` must be a JSON object."},
                status=400,
            )

        try:
            status_value = run_single_scenario(
                tenant, code, payload_override=payload_override,
            )
        except ValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        if status_value == "unknown_code":
            return Response(
                {"detail": f"Unknown scenario code {code!r}."},
                status=400,
            )
        row = (
            FbrScenarioTest.objects
            .filter(tenant_id=request.tenant_id, scenario_code=code)
            .first()
        )
        return Response({
            "status": status_value,
            "scenario": FbrScenarioTestSerializer(row).data if row else None,
        })

    # ----- Template library --------------------------------------------
    #
    # Two operations + one list endpoint:
    #
    #   GET  /api/fbr/scenarios/templates/                  → list
    #   POST /api/fbr/scenarios/SN001/save-template/        → save current
    #   POST /api/fbr/scenarios/SN001/apply-template/<id>/  → apply + run
    #
    # Save-template is super-admin only (template library is platform-
    # level). Apply-template is also super-admin only since it touches
    # an external system (PRAL) using stored credentials.

    @action(detail=False, methods=["get"], url_path="templates",
            permission_classes=[IsTenantMember])
    def list_templates(self, request):
        """List every saved template across all scenarios. Used by the
        admin-web 'Apply template' picker when seeding a new tenant."""
        from .models import ScenarioPayloadTemplate
        qs = ScenarioPayloadTemplate.objects.order_by(
            "scenario_code", "name",
        )
        # Optional filter by scenario_code for the per-card "apply
        # template" dropdown.
        code = request.query_params.get("scenario_code")
        if code:
            qs = qs.filter(scenario_code=code.upper())
        results = [
            {
                "id": str(t.id),
                "name": t.name,
                "scenario_code": t.scenario_code,
                "notes": t.notes,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in qs
        ]
        return Response({"results": results})

    @action(detail=False, methods=["post"],
            url_path=r"(?P<code>SN\d{3})/save-template",
            permission_classes=[HasRolePerm.with_perm("fbr.tokens.manage")])
    def save_template(self, request, code: str):
        """Save the scenario's most recent successful (or operator-
        edited) payload as a reusable template.

        Body:
          { "name": "Wholesaler/Retailer pack",
            "payload": { ...the full PRAL request JSON... },
            "notes": "optional super-admin notes" }
        """
        from .services import save_payload_as_template
        if not request.user.is_superuser:
            return Response(
                {"detail": "Only super-admin can save scenario templates."},
                status=403,
            )
        code = code.upper()
        data = request.data if isinstance(request.data, dict) else {}
        name = (data.get("name") or "").strip()
        payload = data.get("payload")
        notes = (data.get("notes") or "").strip()
        if not name:
            return Response(
                {"detail": "`name` is required."}, status=400,
            )
        if not isinstance(payload, dict):
            return Response(
                {"detail": "`payload` must be a JSON object."}, status=400,
            )
        tenant = Tenant.objects.get(pk=request.tenant_id)
        template = save_payload_as_template(
            name=name,
            scenario_code=code,
            payload=payload,
            seller_tenant=tenant,
            created_by=request.user,
            notes=notes,
        )
        return Response({
            "id": str(template.id),
            "name": template.name,
            "scenario_code": template.scenario_code,
            "created_at": template.created_at.isoformat(),
        }, status=201)

    @action(detail=False, methods=["post"],
            url_path=r"(?P<code>SN\d{3})/apply-template/(?P<template_id>[^/]+)",
            permission_classes=[HasRolePerm.with_perm("fbr.tokens.manage")])
    def apply_template(self, request, code: str, template_id: str):
        """Apply a saved template to THIS tenant's scenario and post to
        PRAL. Substitutes the template's seller placeholders with the
        target tenant's seller block, then runs as a one-off override.
        """
        from .models import ScenarioPayloadTemplate
        from .services import apply_template_payload, run_single_scenario

        if not request.user.is_superuser:
            return Response(
                {"detail": "Only super-admin can apply scenario templates."},
                status=403,
            )
        code = code.upper()
        try:
            template = ScenarioPayloadTemplate.objects.get(pk=template_id)
        except ScenarioPayloadTemplate.DoesNotExist:
            return Response(
                {"detail": "Template not found."}, status=404,
            )
        if template.scenario_code != code:
            return Response(
                {"detail":
                    f"Template is for {template.scenario_code}, "
                    f"not {code}."},
                status=400,
            )
        tenant = Tenant.objects.get(pk=request.tenant_id)
        materialised = apply_template_payload(template, tenant)
        try:
            status_value = run_single_scenario(
                tenant, code, payload_override=materialised,
            )
        except ValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        row = (
            FbrScenarioTest.objects
            .filter(tenant_id=request.tenant_id, scenario_code=code)
            .first()
        )
        return Response({
            "status": status_value,
            "scenario": FbrScenarioTestSerializer(row).data if row else None,
            "applied_template": {
                "id": str(template.id), "name": template.name,
            },
        })


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
