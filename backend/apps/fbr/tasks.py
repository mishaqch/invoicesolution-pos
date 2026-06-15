"""FBR Celery tasks.

  - submit_invoice_to_fbr: per-invoice. Posts to PRAL, persists submission,
    transitions invoice status. Retries with exponential backoff (sync-engine
    schedule) on transient errors.
  - finalize_aged_invoices: hourly beat. Transitions invoices past their
    edit_deadline_at to status='finalized'.
  - recompute_monthly_budgets: 00:05 on the 1st of each month (PKT).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.notifications.services import notify
from apps.sales.models import Invoice
from apps.tenants.models import Tenant

from .budget import compute_edit_deadline, recompute_monthly_budget
from .builder import build_invoice_payload
from .client import (
    FbrClient,
    PralAuthError,
    PralBusinessError,
    PralError,
    PralTransientError,
    PralValidationError,
)
from .models import BranchFbrToken, FbrSubmission, FbrToken
from .qr import build_qr_payload, render_png_b64

logger = logging.getLogger(__name__)


# Backoff schedule for transient FBR errors (mirrors the sync worker).
_BACKOFF_S = [10, 30, 120, 600, 3600, 21600]


@shared_task(name="fbr.submit_invoice_to_fbr", bind=True, max_retries=len(_BACKOFF_S))
def submit_invoice_to_fbr(self, invoice_id: str) -> dict:
    """Submit one invoice to PRAL and persist the result."""
    invoice = (
        Invoice.objects.select_related("tenant", "branch")
        .prefetch_related("items")
        .get(pk=invoice_id)
    )

    if invoice.status not in ("pending_sync", "submitted", "failed"):
        logger.info("Skipping FBR submit for %s — status=%s", invoice_id, invoice.status)
        return {"skipped": True, "status": invoice.status}

    tenant: Tenant = invoice.tenant

    # --- SDC (Fiscalization Service) path — evaluated FIRST ---------------
    # POS/IMS-type registrations fiscalize through the SDC (a central Windows
    # service holding the POS ID + Code), NOT via our DI-API tokens. So if the
    # SDC is configured AND this branch has an FBR POS ID, route here BEFORE any
    # token logic — these tenants have no DI-API Bearer token at all. One SDC
    # serves many POS IDs (POSID is per-request). DI-API tenants (no SDC
    # configured, or branch without a POS ID) fall through to the token path.
    from apps.fbr import sdc_client

    branch_pos_id = getattr(invoice.branch, "fbr_pos_id", None)
    if sdc_client.sdc_configured() and branch_pos_id:
        return _submit_via_sdc(self, invoice=invoice, tenant=tenant, pos_id=branch_pos_id)

    # --- Token selection -------------------------------------------------
    # POS: each branch is its own registered POS with its OWN bearer token
    # (BranchFbrToken). If the invoice's branch has an FBR token configured,
    # that branch token is authoritative — its sales MUST go out under it,
    # never under a different branch's or the tenant's token. If the branch
    # token exists but is inactive, defer (don't silently fall back to the
    # tenant token and mis-attribute the sale to the wrong POS registration).
    #
    # Digital Invoicing: a DI tenant has no per-branch POS registration, so
    # there's no BranchFbrToken and we fall through to the tenant-level token
    # logic below — unchanged.
    # `token` ends up being either a BranchFbrToken (POS) or a tenant
    # FbrToken (Digital Invoicing). Both expose `.token`, `.environment` and
    # `.api_endpoint`, so everything downstream is identical.
    branch_token_qs = BranchFbrToken.objects.filter(branch_id=invoice.branch_id)
    if branch_token_qs.exists():
        token = branch_token_qs.filter(is_active=True).first()
        if token is None:
            logger.warning(
                "Branch %s has an FBR token but it's inactive — deferring "
                "(refusing to submit a POS sale under a different token)",
                invoice.branch_id,
            )
            return {"deferred": "branch_token_inactive"}
    else:
        # Tenant-level token (Digital Invoicing). Production-only once
        # production exists. If the tenant has ANY production token row, we use
        # the active production token and NEVER fall back to sandbox — even if
        # production is temporarily inactive (e.g. revoked by a PralAuthError).
        # Falling back would route live sales to the sandbox endpoint, which
        # must never happen. Sandbox is only eligible for tenants that never
        # went to production. activate_production_token() also deactivates the
        # sandbox token; this is the belt-and-braces guard.
        has_production = FbrToken.objects.filter(
            tenant=tenant, environment="production",
        ).exists()
        if has_production:
            token = FbrToken.objects.filter(
                tenant=tenant, environment="production", is_active=True,
            ).first()
            if token is None:
                logger.warning(
                    "Production token for tenant %s is inactive — deferring "
                    "(refusing sandbox fallback for a production tenant)",
                    tenant.id,
                )
                return {"deferred": "production_inactive"}
        else:
            token = FbrToken.objects.filter(
                tenant=tenant, environment="sandbox", is_active=True,
            ).first()
    if token is None:
        # No token — leave the invoice in pending_sync. Onboarding will
        # set the token; nothing to retry meanwhile.
        logger.info("No FBR token for tenant %s — deferring submission", tenant.id)
        return {"deferred": "no_token"}

    environment = token.environment
    # Sandbox always needs a scenarioId; production ignores it (PRAL classifies
    # per-line via saleType in production). We pick the most specific scenario
    # the invoice matches, preferring retail/end-consumer scenarios when the
    # tenant is assigned them — see the detailed selection block below.
    #   - 3rd-Schedule lines (retail-price-fixed) → SN008 (or retail SN027)
    #     (PRAL rejects SN001/SN002 for 3rd-Schedule lines with errorCode
    #     0122 — "Value of Sales Excl. ST and Retail Price must be > 0".)
    #   - Reduced-rate lines (8th Schedule)       → SN005 (or retail SN028)
    #   - Standard, registered buyer (NTN on file) → SN001
    #   - Standard, walk-in / unregistered         → SN002 (or retail SN026)
    # Hard-coding SN001 was a sandbox-only bug — PRAL rejects SN001 with
    # errorCode 0205 when the buyer NTN isn't in PRAL's registered-buyer
    # table. See feedback_pral_sandbox_quirks.md.
    # Choose the sandbox scenarioId (None in production). Shared with the
    # "Validate with FBR" action so validate + submit always agree — see
    # scenarios.pick_scenario_id for the full selection rules. (Production
    # classifies per-line via saleType, so scenario_id is None there.)
    from apps.fbr.scenarios import pick_scenario_id

    scenario_id = pick_scenario_id(invoice, environment)

    # If the invoice mixes line types, PRAL's sandbox may reject the chosen
    # scenario for the odd line. Log so we can spot it in support.
    if environment == "sandbox":
        items = list(invoice.items.all())
        has_any_third = any(
            i.fixed_notified_value is not None and i.fixed_notified_value > 0
            for i in items
        )
        all_third = bool(items) and all(
            i.fixed_notified_value is not None and i.fixed_notified_value > 0
            for i in items
        )
        if has_any_third and not all_third:
            logger.info(
                "Mixed-content invoice %s: submitting under %s; "
                "sandbox may reject the 3rd-Schedule lines if PRAL "
                "enforces per-line scenario-saleType matching.",
                invoice_id, scenario_id,
            )
    payload = build_invoice_payload(
        invoice, environment=environment, scenario_id=scenario_id,
    )

    invoice.status = "submitted"
    invoice.fbr_submitted_at = timezone.now()
    invoice.save(update_fields=["status", "fbr_submitted_at", "updated_at"])

    # --- DI-API path (direct to PRAL gateway) -----------------------------
    client = FbrClient(
        environment=environment,
        token=token.token,
        endpoint_base=token.api_endpoint or _default_endpoint_base(),
    )

    attempt_number = self.request.retries + 1
    try:
        result = client.post_invoice(payload)
    except PralTransientError as exc:
        _log_failed_submission(
            tenant_id=tenant.id, invoice=invoice, environment=environment,
            endpoint="postinvoicedata", request_payload=payload,
            attempt_number=attempt_number, exc=exc,
        )
        attempt_idx = self.request.retries
        if attempt_idx >= len(_BACKOFF_S):
            _mark_invoice_failed(invoice, str(exc))
            return {"failed": "max_retries", "error": str(exc)}
        countdown = _BACKOFF_S[attempt_idx]
        logger.warning(
            "Transient PRAL error for %s (attempt %s); retry in %ss: %s",
            invoice_id, attempt_idx + 1, countdown, exc,
        )
        raise self.retry(exc=exc, countdown=countdown)
    except PralAuthError as exc:
        _log_failed_submission(
            tenant_id=tenant.id, invoice=invoice, environment=environment,
            endpoint="postinvoicedata", request_payload=payload,
            attempt_number=attempt_number, exc=exc,
        )
        # Deactivate whichever token failed — branch token (POS) or tenant
        # token (DI). type(token) resolves to the right model/table.
        type(token).objects.filter(pk=token.pk).update(is_active=False)
        notify(
            tenant_id=tenant.id,
            notification_type="fbr.auth_error",
            title="FBR token revoked or expired",
            message="Re-authenticate via IRIS and provide a new token.",
            severity="danger",
        )
        _mark_invoice_failed(invoice, f"Auth error: {exc}")
        return {"failed": "auth"}
    except (PralValidationError, PralBusinessError) as exc:
        _log_failed_submission(
            tenant_id=tenant.id, invoice=invoice, environment=environment,
            endpoint="postinvoicedata", request_payload=payload,
            attempt_number=attempt_number, exc=exc,
        )
        _mark_invoice_failed(invoice, str(exc))
        notify(
            tenant_id=tenant.id,
            notification_type="fbr.submission_failed",
            title=f"FBR submission failed: {invoice.local_invoice_number}",
            message=str(exc)[:500],
            severity="warning",
            data={"invoice_id": str(invoice.id), "error_code": exc.error_code},
        )
        return {"failed": "permanent", "error_code": exc.error_code}
    except PralError as exc:
        _log_failed_submission(
            tenant_id=tenant.id, invoice=invoice, environment=environment,
            endpoint="postinvoicedata", request_payload=payload,
            attempt_number=attempt_number, exc=exc,
        )
        _mark_invoice_failed(invoice, str(exc))
        return {"failed": "unknown", "error": str(exc)}

    # ---- Success ----
    FbrSubmission.objects.create(
        tenant_id=tenant.id,
        invoice=invoice,
        environment=environment,
        endpoint="postinvoicedata",
        request_payload=payload,
        response_payload=result.body,
        http_status=result.http_status,
        status_code=result.status_code,
        fbr_invoice_number=result.fbr_invoice_number,
        attempt_number=attempt_number,
        duration_ms=result.duration_ms,
    )

    fbr_no = result.fbr_invoice_number or ""
    qr_payload = build_qr_payload(
        fbr_invoice_number=fbr_no,
        validated_at=timezone.now(),
        amount=invoice.grand_total,
        seller_ntn=tenant.ntn,
    )
    _persist_fbr_success(invoice, tenant, fbr_no, qr_payload)
    return {"ok": True, "fbr_invoice_number": fbr_no}


def _submit_via_sdc(self, *, invoice, tenant, pos_id: str) -> dict:
    """Fiscalize an invoice through the SDC (Fiscalization Service) for the
    given branch POS ID. Persists the fiscal number + QR on success. Mirrors
    the DI-API retry/fail semantics. Used for POS/IMS-type registrations."""
    from apps.fbr import sdc_client

    invoice.status = "submitted"
    invoice.fbr_submitted_at = timezone.now()
    invoice.save(update_fields=["status", "fbr_submitted_at", "updated_at"])

    attempt = self.request.retries + 1

    def _log_failure(exc):
        # SDC errors aren't PralError; write a row directly using valid
        # field choices (environment/endpoint).
        FbrSubmission.objects.create(
            tenant_id=tenant.id, invoice=invoice, environment="production",
            endpoint="postinvoicedata",
            request_payload={"POSID": pos_id, "via": "SDC"},
            response_payload=None, http_status=None, status_code="01",
            attempt_number=attempt, error_message=str(exc)[:1000],
        )

    try:
        sdc_res = sdc_client.submit_invoice(invoice=invoice, pos_id=pos_id)
    except sdc_client.SdcTransientError as exc:
        _log_failure(exc)
        attempt_idx = self.request.retries
        if attempt_idx >= len(_BACKOFF_S):
            _mark_invoice_failed(invoice, str(exc))
            return {"failed": "max_retries", "error": str(exc)}
        logger.warning("Transient SDC error for %s; retry in %ss: %s",
                       invoice.id, _BACKOFF_S[attempt_idx], exc)
        raise self.retry(exc=exc, countdown=_BACKOFF_S[attempt_idx])
    except sdc_client.SdcRejectedError as exc:
        _log_failure(exc)
        _mark_invoice_failed(invoice, str(exc))
        notify(
            tenant_id=tenant.id, notification_type="fbr.submission_failed",
            title=f"FBR (SDC) submission failed: {invoice.local_invoice_number}",
            message=str(exc)[:500], severity="warning",
            data={"invoice_id": str(invoice.id)},
        )
        return {"failed": "sdc_rejected", "error": str(exc)}

    fbr_no = sdc_res.fbr_invoice_number
    qr_payload = sdc_res.qr_payload or build_qr_payload(
        fbr_invoice_number=fbr_no, validated_at=timezone.now(),
        amount=invoice.grand_total, seller_ntn=tenant.ntn,
    )
    FbrSubmission.objects.create(
        tenant_id=tenant.id, invoice=invoice, environment="production",
        endpoint="postinvoicedata",
        request_payload={"POSID": pos_id, "via": "SDC"},
        response_payload=sdc_res.raw, http_status=200, status_code="00",
        fbr_invoice_number=fbr_no, attempt_number=attempt,
    )
    _persist_fbr_success(invoice, tenant, fbr_no, qr_payload)
    return {"ok": True, "fbr_invoice_number": fbr_no, "via": "sdc"}


def _persist_fbr_success(invoice, tenant, fbr_no: str, qr_payload: str) -> None:
    """Shared success persistence for both the DI-API and SDC paths: stamp the
    FBR number + QR, set the edit deadline, flip status to valid, audit-log."""
    validated_at = timezone.now()
    invoice.fbr_invoice_number = fbr_no
    invoice.fbr_qr_payload = qr_payload
    invoice.fbr_validated_at = validated_at
    invoice.edit_deadline_at = compute_edit_deadline(invoice.fbr_submitted_at or validated_at)
    invoice.status = "valid"
    invoice.save(update_fields=[
        "fbr_invoice_number", "fbr_qr_payload", "fbr_validated_at",
        "edit_deadline_at", "status", "updated_at",
    ])
    audit_log(
        tenant_id=tenant.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="fbr_validated",
        after={"fbr_invoice_number": fbr_no},
    )


@shared_task(name="fbr.finalize_aged_invoices")
def finalize_aged_invoices() -> dict:
    """Hourly beat. Move past-deadline invoices to 'finalized'.

    No FBR call — PRAL has already moved them server-side. This is purely
    our local lifecycle marker so rules.py refuses edits/cancels.
    """
    now = timezone.now()
    qs = Invoice.objects.filter(
        edit_deadline_at__lt=now,
        status__in=[
            "valid", "edited", "partially_edited",
            "partially_cancelled", "partially_edited_and_cancelled",
        ],
    )
    count = qs.update(status="finalized", updated_at=now)
    return {"finalized": count}


@shared_task(name="fbr.recompute_monthly_budgets")
def recompute_monthly_budgets() -> dict:
    """00:05 PKT on the 1st of each month: refresh every active tenant."""
    refreshed = 0
    for tenant in Tenant.objects.filter(subscription_status__in=["trial", "active"]):
        try:
            recompute_monthly_budget(tenant)
            refreshed += 1
        except Exception as exc:  # never let one tenant break the batch
            logger.exception("recompute_monthly_budget failed for %s: %s", tenant.id, exc)
    return {"refreshed": refreshed}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_failed_submission(
    *, tenant_id, invoice, environment, endpoint, request_payload, attempt_number,
    exc: PralError,
) -> None:
    """Append a failure row. fbr_submissions is append-only — single INSERT."""
    FbrSubmission.objects.create(
        tenant_id=tenant_id,
        invoice=invoice,
        environment=environment,
        endpoint=endpoint,
        request_payload=request_payload,
        response_payload=exc.response,
        http_status=exc.http_status,
        status_code="01",
        attempt_number=attempt_number,
        error_message=str(exc),
    )


def _mark_invoice_failed(invoice: Invoice, message: str) -> None:
    invoice.status = "failed"
    invoice.save(update_fields=["status", "updated_at"])


def _default_endpoint_base() -> str:
    """Fallback endpoint base for tokens that didn't explicitly set one."""
    return "https://gw.fbr.gov.pk"
