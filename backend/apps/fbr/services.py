"""FBR orchestration services beyond the per-invoice submit task.

  - run_scenarios: invoke each eligible scenario in sandbox, persist results.
  - cancel_invoice_with_fbr / edit_invoice_item_with_fbr: rules check →
    budget consume → PRAL call → persist + audit + transition status.
  - activate_production_token: verifies all eligible scenarios are green
    and switches the tenant from sandbox to production.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.sales.models import Invoice, SaleItem, SaleItemHistory
from apps.tenants.models import Tenant

from .budget import consume_cancel_budget
from .builder import build_invoice_payload
from .client import FbrClient
from .models import FbrScenarioTest, FbrSubmission, FbrToken
from .rules import can_cancel_invoice, can_cancel_item, can_edit_item
from .scenarios import SCENARIOS, eligible_scenarios

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sandbox scenario runner
# ---------------------------------------------------------------------------


def run_scenarios(tenant: Tenant) -> dict:
    """Run every eligible scenario against the sandbox endpoint.

    Returns a dict {scenario_code: status}. Persists FbrScenarioTest rows.
    Each call is logged to FbrSubmission for full traceability.
    """
    token = (
        FbrToken.objects.filter(tenant=tenant, environment="sandbox", is_active=True).first()
    )
    if token is None:
        raise ValidationError("Sandbox token is not configured.")

    client = FbrClient(
        environment="sandbox",
        token=token.token,
        endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
    )

    results: dict[str, str] = {}
    for meta in eligible_scenarios(tenant):
        payload = meta.builder(tenant)
        scenario_test, _ = FbrScenarioTest.objects.update_or_create(
            tenant=tenant, scenario_code=meta.code,
            defaults={
                "scenario_description": meta.description,
                "status": "submitting",
                "last_attempt_at": timezone.now(),
                "error_message": None,
            },
        )
        try:
            result = client.post_invoice(payload)
        except Exception as exc:
            scenario_test.status = "failed"
            scenario_test.error_message = str(exc)[:500]
            scenario_test.save(update_fields=[
                "status", "error_message", "last_attempt_at", "updated_at",
            ])
            FbrSubmission.objects.create(
                tenant=tenant, environment="sandbox", endpoint="postinvoicedata",
                request_payload=payload, error_message=str(exc),
                status_code="01", attempt_number=1,
            )
            results[meta.code] = "failed"
            continue

        scenario_test.status = "success"
        scenario_test.fbr_invoice_number = result.fbr_invoice_number
        scenario_test.error_message = None
        scenario_test.save(update_fields=[
            "status", "fbr_invoice_number", "error_message",
            "last_attempt_at", "updated_at",
        ])
        FbrSubmission.objects.create(
            tenant=tenant, environment="sandbox", endpoint="postinvoicedata",
            request_payload=payload, response_payload=result.body,
            http_status=result.http_status, status_code=result.status_code,
            fbr_invoice_number=result.fbr_invoice_number,
            duration_ms=result.duration_ms, attempt_number=1,
        )
        results[meta.code] = "success"

    return results


def all_scenarios_passed(tenant: Tenant) -> bool:
    eligible = {meta.code for meta in eligible_scenarios(tenant)}
    if not eligible:
        return False
    passed = set(
        FbrScenarioTest.objects.filter(
            tenant=tenant, scenario_code__in=eligible, status="success",
        ).values_list("scenario_code", flat=True)
    )
    return eligible.issubset(passed)


# ---------------------------------------------------------------------------
# Production activation
# ---------------------------------------------------------------------------


@transaction.atomic
def activate_production_token(*, tenant: Tenant, token: str, api_endpoint: str) -> FbrToken:
    if not all_scenarios_passed(tenant):
        raise ValidationError(
            "All eligible sandbox scenarios must pass before activating "
            "production. Run the scenarios from the FBR dashboard."
        )
    obj, _ = FbrToken.objects.update_or_create(
        tenant=tenant, environment="production",
        defaults={
            "api_endpoint": api_endpoint,
            "is_active": True,
            "activated_at": timezone.now(),
        },
    )
    obj.set_token(token)
    obj.save(update_fields=["token_encrypted", "updated_at"])
    audit_log(
        tenant_id=tenant.id, entity_type="fbr_token",
        entity_id=obj.id, action="activate_production",
    )
    return obj


# ---------------------------------------------------------------------------
# Cancel an invoice with FBR
# ---------------------------------------------------------------------------


@transaction.atomic
def cancel_invoice_with_fbr(
    invoice: Invoice, *, reason: str, user=None, request=None,
) -> Invoice:
    """Cancel via PRAL: rules check → budget consume → API call → status flip.

    Phase 4 ships the synchronous path (admin UI calls this). The PRAL
    cancellation API isn't documented in v1.6 with a precise wire shape;
    we send a minimal payload and rely on the response.
    """
    allowed, why = can_cancel_invoice(invoice)
    if not allowed:
        raise ValidationError({"detail": why})

    consume_cancel_budget(
        tenant=invoice.tenant, invoice=invoice, action_type="cancel", user=user,
    )

    token = FbrToken.objects.filter(
        tenant=invoice.tenant, environment="production", is_active=True,
    ).first()

    if token is not None and invoice.fbr_invoice_number:
        client = FbrClient(
            environment="production", token=token.token,
            endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
        )
        cancel_payload = {
            "invoiceNumber": invoice.fbr_invoice_number,
            "reason": reason[:500],
        }
        try:
            result = client.cancel_invoice(cancel_payload)
            FbrSubmission.objects.create(
                tenant_id=invoice.tenant_id, invoice=invoice,
                environment="production", endpoint="cancelinvoice",
                request_payload=cancel_payload,
                response_payload=result.body, http_status=result.http_status,
                status_code=result.status_code,
                duration_ms=result.duration_ms, attempt_number=1,
            )
        except Exception as exc:
            FbrSubmission.objects.create(
                tenant_id=invoice.tenant_id, invoice=invoice,
                environment="production", endpoint="cancelinvoice",
                request_payload=cancel_payload, error_message=str(exc),
                status_code="01", attempt_number=1,
            )
            raise ValidationError(
                {"detail": f"PRAL rejected the cancel: {exc}"}
            )

    # Local lifecycle: from cancellation.py we already know how to revert
    # stock; re-use it here so behavior matches the admin "cancel sale" path.
    from apps.sales.services.cancellation import cancel_invoice as local_cancel
    local_cancel(invoice, reason=reason, user=user, request=request)
    return invoice
