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
from .models import FbrSubmission, FbrToken
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
    token = (
        FbrToken.objects.filter(tenant=tenant, environment="production", is_active=True)
        .first()
        or FbrToken.objects.filter(tenant=tenant, environment="sandbox", is_active=True).first()
    )
    if token is None:
        # No token — leave the invoice in pending_sync. Onboarding will
        # set the token; nothing to retry meanwhile.
        logger.info("No FBR token for tenant %s — deferring submission", tenant.id)
        return {"deferred": "no_token"}

    environment = token.environment
    payload = build_invoice_payload(
        invoice,
        environment=environment,
        # Sandbox always needs a scenarioId; pick SN001 by default for
        # real (non-test) sandbox traffic so the request is well-formed.
        scenario_id="SN001" if environment == "sandbox" else None,
    )

    invoice.status = "submitted"
    invoice.fbr_submitted_at = timezone.now()
    invoice.save(update_fields=["status", "fbr_submitted_at", "updated_at"])

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
        FbrToken.objects.filter(pk=token.pk).update(is_active=False)
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

    validated_at = timezone.now()
    fbr_no = result.fbr_invoice_number or ""
    qr_payload = build_qr_payload(
        fbr_invoice_number=fbr_no,
        validated_at=validated_at,
        amount=invoice.grand_total,
        seller_ntn=tenant.ntn,
    )

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
    return {"ok": True, "fbr_invoice_number": fbr_no}


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
