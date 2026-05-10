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


# ---------------------------------------------------------------------------
# Edit a line item with FBR
# ---------------------------------------------------------------------------


# Fields a tenant is allowed to edit on a sale item via the API. Snapshot
# fields (product_name, sku, hs_code, uom, sale_type, line_number) stay
# immutable — those are what FBR keyed off when validating the original.
_EDITABLE_FIELDS = ("quantity", "unit_price", "tax_rate")


@transaction.atomic
def edit_invoice_item_with_fbr(
    invoice: Invoice, item: SaleItem, *,
    new_values: dict,
    reason: str,
    user=None,
    request=None,
) -> SaleItem:
    """Edit a single line item on an FBR-validated invoice.

    Flow (mirrors cancel_invoice_with_fbr):
      1. Rules check (72h window, edit_count < 1, not Annexure-C linked).
      2. Snapshot the SaleItem to SaleItemHistory before mutation.
      3. Apply the new values + recompute derived fields (tax_amount,
         discount_amount, line_total) and the parent invoice totals.
      4. Call PRAL editinvoice with the FULL re-built payload that
         reflects the new line. PRAL validates, returns 00 or rejects.
      5. On success: persist FbrSubmission row, flip is_edited + status,
         budget consume, audit log. On failure: rollback the txn so the
         line stays as it was.

    The 10% monthly cancel-budget DOES apply to edits per FBR §4.1.2 —
    consume_cancel_budget is called with action_type="edit".
    """
    allowed, why = can_edit_item(invoice, item)
    if not allowed:
        raise ValidationError({"detail": why})

    # Validate the incoming patch — only whitelisted fields, all positive.
    cleaned: dict = {}
    for k, v in new_values.items():
        if k not in _EDITABLE_FIELDS:
            raise ValidationError({k: f"Field '{k}' is not editable."})
        try:
            d = Decimal(str(v))
        except Exception:
            raise ValidationError({k: f"'{v}' is not a number."})
        if d < 0:
            raise ValidationError({k: f"'{k}' must not be negative."})
        cleaned[k] = d

    if not cleaned:
        raise ValidationError({"detail": "No editable fields supplied."})

    # Snapshot before mutation — required by PRAL spec (originals must
    # remain viewable).
    SaleItemHistory.objects.create(
        sale_item=item,
        changed_by=user,
        change_type="edit",
        previous_data={
            "quantity": str(item.quantity),
            "unit_price": str(item.unit_price),
            "tax_rate": str(item.tax_rate),
            "tax_amount": str(item.tax_amount),
            "discount_amount": str(item.discount_amount),
            "line_total": str(item.line_total),
            "reason": reason,
        },
    )

    # Apply patch + recompute derived money fields. Mirrors the math in
    # checkout.create_invoice but for a single line.
    if "quantity" in cleaned:
        item.quantity = cleaned["quantity"]
    if "unit_price" in cleaned:
        item.unit_price = cleaned["unit_price"]
    if "tax_rate" in cleaned:
        item.tax_rate = cleaned["tax_rate"]

    gross = item.quantity * item.unit_price
    if item.discount_pct:
        item.discount_amount = (gross * item.discount_pct / Decimal("100")).quantize(
            Decimal("0.0001"),
        )
    taxable = gross - item.discount_amount
    item.tax_amount = (taxable * item.tax_rate / Decimal("100")).quantize(
        Decimal("0.0001"),
    )
    item.line_total = (taxable + item.tax_amount).quantize(Decimal("0.0001"))

    item.is_edited = True
    item.edited_at = timezone.now()
    item.edit_count = (item.edit_count or 0) + 1
    item.save(update_fields=[
        "quantity", "unit_price", "tax_rate",
        "discount_amount", "tax_amount", "line_total",
        "is_edited", "edited_at", "edit_count",
    ])

    # Recompute parent invoice totals from the (now-edited) item set.
    items = list(invoice.items.all())
    invoice.subtotal = sum(
        (it.quantity * it.unit_price for it in items if not it.is_cancelled),
        Decimal("0"),
    )
    invoice.discount_total = sum(
        (it.discount_amount for it in items if not it.is_cancelled),
        Decimal("0"),
    )
    invoice.tax_total = sum(
        (it.tax_amount for it in items if not it.is_cancelled),
        Decimal("0"),
    )
    invoice.grand_total = sum(
        (it.line_total for it in items if not it.is_cancelled),
        Decimal("0"),
    )

    # Status flip — same logic as per-item cancel.
    if any(it.is_edited for it in items) and any(it.is_cancelled for it in items):
        invoice.status = "partially_edited_and_cancelled"
    elif all(it.is_edited or it.is_cancelled for it in items):
        invoice.status = "edited" if all(it.is_edited for it in items) else "edited"
    else:
        invoice.status = "partially_edited"
    invoice.save(update_fields=[
        "subtotal", "discount_total", "tax_total", "grand_total",
        "status", "updated_at",
    ])

    # Budget — edits count against the 10% monthly cap, same as cancels.
    consume_cancel_budget(
        tenant=invoice.tenant, invoice=invoice, action_type="edit", user=user,
    )

    # Push the edit to PRAL when we have a token + the invoice has an
    # FBR invoice number. In sandbox/dev with no token configured, we
    # still record the edit locally so the audit trail stays intact.
    token = FbrToken.objects.filter(
        tenant=invoice.tenant, environment="production", is_active=True,
    ).first()
    if token is not None and invoice.fbr_invoice_number:
        # Re-build the canonical FBR payload reflecting the new line state.
        # editinvoice expects the FBR invoice number plus the full document.
        edit_payload = build_invoice_payload(invoice, environment="production")
        edit_payload["invoiceNumber"] = invoice.fbr_invoice_number
        edit_payload["editReason"] = reason[:500]
        client = FbrClient(
            environment="production", token=token.token,
            endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
        )
        try:
            result = client.edit_invoice(edit_payload)
            FbrSubmission.objects.create(
                tenant_id=invoice.tenant_id, invoice=invoice,
                environment="production", endpoint="editinvoice",
                request_payload=edit_payload,
                response_payload=result.body, http_status=result.http_status,
                status_code=result.status_code,
                duration_ms=result.duration_ms, attempt_number=1,
            )
        except Exception as exc:
            FbrSubmission.objects.create(
                tenant_id=invoice.tenant_id, invoice=invoice,
                environment="production", endpoint="editinvoice",
                request_payload=edit_payload, error_message=str(exc),
                status_code="01", attempt_number=1,
            )
            raise ValidationError({"detail": f"PRAL rejected the edit: {exc}"})

    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="sale_item", entity_id=item.id, action="edit",
        after={"reason": reason, "fields": list(cleaned.keys())},
        request=request,
    )
    return item


# ---------------------------------------------------------------------------
# Resubmit a failed invoice
# ---------------------------------------------------------------------------


def resubmit_failed_invoice(invoice: Invoice, *, user=None, request=None) -> Invoice:
    """Re-trigger FBR submission for an invoice that failed.

    The submit task already accepts status='failed' and idempotently
    handles the retry. We just queue it. Marking back to pending_sync
    here would race the task; let it set status='submitted' itself.
    """
    if invoice.status not in ("failed", "pending_sync"):
        raise ValidationError({
            "detail": f"Only failed/pending invoices can be resubmitted "
                      f"(this one is {invoice.status}).",
        })
    if invoice.fbr_invoice_number:
        # Already got an FBR number — nothing to resubmit.
        raise ValidationError({
            "detail": "This invoice already has an FBR invoice number.",
        })

    from .tasks import submit_invoice_to_fbr
    submit_invoice_to_fbr.delay(str(invoice.id))

    audit_log(
        tenant_id=invoice.tenant_id, user=user,
        entity_type="invoice", entity_id=invoice.id, action="resubmit",
        after={"previous_status": invoice.status},
        request=request,
    )
    return invoice
