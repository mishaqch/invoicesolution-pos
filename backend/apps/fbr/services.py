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
from .models import (
    BranchFbrToken,
    FbrScenarioTest,
    FbrSubmission,
    FbrToken,
    ScenarioPayloadTemplate,
)
from .rules import can_cancel_invoice, can_cancel_item, can_edit_item
from .scenarios import SCENARIOS, eligible_scenarios

logger = logging.getLogger(__name__)


def token_for_invoice(invoice: Invoice):
    """Return the FBR token that owns this invoice's submissions.

    POS: the invoice's branch has its own BranchFbrToken — use it, so a
    cancel/edit goes to PRAL under the SAME registered POS that posted the
    original. DI: no branch token → the tenant-level FbrToken (production
    preferred, sandbox fallback). Mirrors the selection in
    tasks.submit_invoice_to_fbr so all PRAL hand-offs for one invoice use one
    consistent credential. Returns None when nothing is configured.
    """
    branch_token = (
        BranchFbrToken.objects.filter(branch_id=invoice.branch_id, is_active=True)
        .first()
    )
    if branch_token is not None:
        return branch_token
    return (
        FbrToken.objects.filter(
            tenant=invoice.tenant, environment="production", is_active=True,
        ).first()
        or FbrToken.objects.filter(
            tenant=invoice.tenant, environment="sandbox", is_active=True,
        ).first()
    )


# ---------------------------------------------------------------------------
# Sandbox scenario runner
# ---------------------------------------------------------------------------


def _make_sandbox_client(tenant: Tenant) -> FbrClient:
    """Build the FbrClient configured for the tenant's sandbox token.
    Raises ValidationError when the token isn't configured."""
    token = (
        FbrToken.objects.filter(tenant=tenant, environment="sandbox", is_active=True).first()
    )
    if token is None:
        raise ValidationError("Sandbox token is not configured.")
    return FbrClient(
        environment="sandbox",
        token=token.token,
        endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
    )


def _run_one_scenario(
    tenant: Tenant, meta, client: FbrClient, *,
    payload_override: dict | None = None,
) -> tuple[str, dict]:
    """Run a single scenario against PRAL sandbox.

    Returns (status, payload) where status ∈ {"success", "failed"}.
    Persists the FbrScenarioTest row AND an FbrSubmission row with
    request + response so the UI's diagnostic panel can render them.

    When `payload_override` is provided, we send that JSON verbatim
    instead of regenerating from the builder. This is the "edit JSON
    on the card and click Send" path — lets the operator iterate on
    PRAL feedback without redeploying code. The override is one-off:
    the builder code remains the source of truth for the next regular
    run.
    """
    payload = payload_override if payload_override is not None else meta.builder(tenant)
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
        # Persist a submission row so the operator can see what we
        # sent and what PRAL replied (or that PRAL hung up).
        response_body = getattr(exc, "response", None) or {"error": str(exc)}
        FbrSubmission.objects.create(
            tenant=tenant, environment="sandbox", endpoint="postinvoicedata",
            request_payload=payload, response_payload=response_body,
            error_message=str(exc)[:500],
            http_status=getattr(exc, "http_status", None),
            status_code="01", attempt_number=1,
        )
        scenario_test.status = "failed"
        scenario_test.error_message = str(exc)[:500]
        scenario_test.save(update_fields=[
            "status", "error_message", "last_attempt_at", "updated_at",
        ])
        return "failed", payload

    FbrSubmission.objects.create(
        tenant=tenant, environment="sandbox", endpoint="postinvoicedata",
        request_payload=payload, response_payload=result.body,
        http_status=result.http_status, status_code=result.status_code,
        fbr_invoice_number=result.fbr_invoice_number,
        duration_ms=result.duration_ms, attempt_number=1,
    )
    scenario_test.status = "success"
    scenario_test.fbr_invoice_number = result.fbr_invoice_number
    scenario_test.error_message = None
    scenario_test.save(update_fields=[
        "status", "fbr_invoice_number", "error_message",
        "last_attempt_at", "updated_at",
    ])
    return "success", payload


def run_single_scenario(
    tenant: Tenant, scenario_code: str, *,
    payload_override: dict | None = None,
) -> str:
    """Run ONE specific scenario by code. Used by the per-scenario
    'Run' button on the admin-web Scenarios page so the operator can
    iterate on a failing scenario without re-running the whole batch.

    `payload_override`: optional. When provided (operator edited the
    JSON in the UI and clicked Send), the override is sent verbatim
    instead of calling the builder. One-off — does not persist.

    Returns the resulting status ("success" | "failed" |
    "not_implemented" | "unknown_code").
    """
    from .scenarios import SCENARIOS, KNOWN_SCENARIO_META, scenario_description

    if scenario_code not in KNOWN_SCENARIO_META:
        return "unknown_code"
    if scenario_code not in SCENARIOS and payload_override is None:
        # Builder unavailable AND no override — record the
        # not_implemented marker. (If the operator pastes a custom
        # payload for an unbuilt code, we honour it.)
        FbrScenarioTest.objects.update_or_create(
            tenant=tenant, scenario_code=scenario_code,
            defaults={
                "scenario_description": scenario_description(scenario_code),
                "status": "not_implemented",
                "last_attempt_at": timezone.now(),
                "error_message": (
                    "Platform doesn't ship a payload-builder for this code."
                ),
            },
        )
        return "not_implemented"

    client = _make_sandbox_client(tenant)
    # If there's no builder but there IS an override, fabricate a
    # minimal meta object so _run_one_scenario can persist the row.
    if scenario_code in SCENARIOS:
        meta = SCENARIOS[scenario_code]
    else:
        from .scenarios import ScenarioMeta
        meta = ScenarioMeta(
            code=scenario_code,
            description=scenario_description(scenario_code),
            sectors=(),
            builder=lambda t: payload_override,
        )
    status, _payload = _run_one_scenario(
        tenant, meta, client, payload_override=payload_override,
    )
    return status


def run_scenarios(tenant: Tenant) -> dict:
    """Run every eligible scenario against the sandbox endpoint.

    Returns a dict {scenario_code: status}. Persists FbrScenarioTest rows.
    Each call is logged to FbrSubmission for full traceability.

    Three statuses possible per scenario:
      - "success"          : PRAL accepted the submission
      - "failed"           : PRAL rejected (with `error_message` set)
      - "not_implemented"  : assigned in IRIS but no builder yet; we
                             skipped without contacting PRAL
    """
    results: dict[str, str] = {}

    # First: surface every assigned scenario that we DON'T have a
    # builder for, with status="not_implemented". The Tenant admin
    # listed it (from IRIS); the operator needs to see it in the runner
    # output even though we didn't contact PRAL for it.
    from .scenarios import assigned_scenario_codes, builder_available, scenario_description
    for code in assigned_scenario_codes(tenant):
        if builder_available(code):
            continue
        FbrScenarioTest.objects.update_or_create(
            tenant=tenant, scenario_code=code,
            defaults={
                "scenario_description": scenario_description(code),
                "status": "not_implemented",
                "last_attempt_at": timezone.now(),
                "error_message": (
                    "This scenario is assigned to the tenant in IRIS but "
                    "the platform doesn't yet ship a payload-builder for "
                    "it. Contact the platform team to add support."
                ),
            },
        )
        results[code] = "not_implemented"

    client = _make_sandbox_client(tenant)
    for meta in eligible_scenarios(tenant):
        status, _ = _run_one_scenario(tenant, meta, client)
        results[meta.code] = status

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
def activate_production_token(
    *, tenant: Tenant, token: str, api_endpoint: str,
    scenarios_cleared_externally: bool = False,
) -> FbrToken:
    """Activate (or reconfigure) the production PRAL token.

    Empty `token` is allowed when an existing production row is
    already present — it means "update the endpoint, keep the
    encrypted bearer in place". On first activation a token is
    required (otherwise there's nothing to save).

    Scenario gate: per the PRAL DI manual, sandbox scenario-based invoices
    must pass before FBR issues a production token — so normally we require
    our own scenario runner to be green first (`all_scenarios_passed`). But a
    POS/tenant that completed sandbox testing directly on the FBR portal (or
    via the IMS) already HAS an FBR-issued production token; its existence is
    itself proof FBR cleared the scenarios. For that case a platform admin can
    set `scenarios_cleared_externally=True` to skip OUR runner check. This
    never bypasses FBR's own requirement — it only acknowledges FBR already
    enforced it. The bypass is recorded in the audit log.
    """
    if not scenarios_cleared_externally and not all_scenarios_passed(tenant):
        raise ValidationError(
            "All eligible sandbox scenarios must pass before activating "
            "production. Run the scenarios from the FBR dashboard. (If FBR "
            "already issued this tenant a production token after sandbox "
            "testing on the FBR portal, a platform admin can activate it "
            "directly.)"
        )
    new_token = (token or "").strip()
    existing = FbrToken.objects.filter(
        tenant=tenant, environment="production",
    ).first()
    if not new_token and existing is None:
        raise ValidationError(
            "Token is required when activating production for the first "
            "time. Paste the production bearer PRAL issued."
        )

    obj, _ = FbrToken.objects.update_or_create(
        tenant=tenant, environment="production",
        defaults={
            "api_endpoint": api_endpoint,
            "is_active": True,
            "activated_at": timezone.now(),
        },
    )
    if new_token:
        obj.set_token(new_token)
        obj.save(update_fields=["token_encrypted", "updated_at"])

    # Once production is live, the sandbox token must NOT be usable. The
    # submission lookup prefers production but falls back to any active
    # sandbox token — so if production were ever deactivated (e.g. a
    # PralAuthError revokes it), live invoices would silently route to the
    # sandbox endpoint. Deactivating sandbox here makes production the only
    # path: no production token → invoices defer cleanly until it's fixed,
    # rather than leaking real sales to sandbox. The row is kept (not
    # deleted) so the bearer/endpoint history survives; it's just inactive.
    sandbox_deactivated = FbrToken.objects.filter(
        tenant=tenant, environment="sandbox", is_active=True,
    ).update(is_active=False, updated_at=timezone.now())

    audit_log(
        tenant_id=tenant.id, entity_type="fbr_token",
        entity_id=obj.id, action="activate_production",
        after={
            "sandbox_deactivated": bool(sandbox_deactivated),
            "scenarios_cleared_externally": bool(scenarios_cleared_externally),
        },
    )
    return obj


# ---------------------------------------------------------------------------
# Per-branch POS token (no scenario / sandbox gate)
# ---------------------------------------------------------------------------


@transaction.atomic
def activate_branch_token(
    *, branch, token: str, api_endpoint: str, environment: str = "production",
):
    """Set (or update) a branch's FBR POS token.

    POS registration on FBR issues the production token directly — there is NO
    sandbox / scenario testing for POS — so unlike `activate_production_token`
    this has no scenario gate. Empty `token` updates only the endpoint when a
    row already exists (the encrypted bearer can't be re-read). The token is
    stored encrypted; the row is keyed (branch, environment) and marked active.
    """
    from .models import BranchFbrToken

    new_token = (token or "").strip()
    existing = BranchFbrToken.objects.filter(
        branch=branch, environment=environment,
    ).first()
    if not new_token and existing is None:
        raise ValidationError(
            "Token is required when adding a branch POS token for the first "
            "time. Paste the bearer FBR issued for this POS."
        )

    obj, _ = BranchFbrToken.objects.update_or_create(
        branch=branch, environment=environment,
        defaults={
            "tenant_id": branch.tenant_id,
            "api_endpoint": api_endpoint,
            "is_active": True,
            "activated_at": timezone.now(),
        },
    )
    if new_token:
        obj.set_token(new_token)
        obj.save(update_fields=["token_encrypted", "updated_at"])

    audit_log(
        tenant_id=branch.tenant_id, entity_type="branch_fbr_token",
        entity_id=obj.id, action="activate_branch_token",
        after={"branch_id": str(branch.id), "environment": environment},
    )
    return obj


@transaction.atomic
def deactivate_branch_token(*, branch, environment: str = "production") -> bool:
    """Deactivate a branch's POS token (kept for history). Returns True if a
    row was changed. While inactive, that branch's sales DEFER rather than
    submit under another token (see tasks.submit_invoice_to_fbr)."""
    from .models import BranchFbrToken

    n = BranchFbrToken.objects.filter(
        branch=branch, environment=environment, is_active=True,
    ).update(is_active=False, updated_at=timezone.now())
    if n:
        audit_log(
            tenant_id=branch.tenant_id, entity_type="branch_fbr_token",
            entity_id=branch.id, action="deactivate_branch_token",
            after={"branch_id": str(branch.id), "environment": environment},
        )
    return bool(n)


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

    # Use the SAME token that owns this invoice's submissions — the branch's
    # POS token if it has one, else the tenant token. (Otherwise the cancel
    # silently never reaches PRAL — the exact bug discovered during the
    # FBR-compliance review — or worse, hits PRAL under the wrong POS.)
    token = token_for_invoice(invoice)

    if token is not None and invoice.fbr_invoice_number:
        client = FbrClient(
            environment=token.environment, token=token.token,
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
                environment=token.environment, endpoint="cancelinvoice",
                request_payload=cancel_payload,
                response_payload=result.body, http_status=result.http_status,
                status_code=result.status_code,
                duration_ms=result.duration_ms, attempt_number=1,
            )
        except Exception as exc:
            FbrSubmission.objects.create(
                tenant_id=invoice.tenant_id, invoice=invoice,
                environment=token.environment, endpoint="cancelinvoice",
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
    token = token_for_invoice(invoice)
    if token is not None and invoice.fbr_invoice_number:
        # Edits amend an already-validated invoice → always the production
        # wire shape (no scenarioId). The token may be a branch POS token or
        # the tenant token; both are production for a validated invoice.
        edit_payload = build_invoice_payload(invoice, environment="production")
        edit_payload["invoiceNumber"] = invoice.fbr_invoice_number
        edit_payload["editReason"] = reason[:500]
        client = FbrClient(
            environment=token.environment, token=token.token,
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


# ---------------------------------------------------------------------------
# Scenario payload templates — save + apply
# ---------------------------------------------------------------------------
#
# Template lifecycle:
#   save_payload_as_template(name, scenario_code, payload, seller_tenant)
#     → Tokenises seller-specific fields so the template is reusable
#       across tenants. Returns the created ScenarioPayloadTemplate.
#
#   apply_template_payload(template, target_tenant)
#     → Substitutes the target tenant's seller values into the template's
#       placeholders and returns the materialised payload. Caller then
#       posts to PRAL via run_single_scenario(payload_override=…).
#
# Tokens used in the JSON template:
#   "{{seller.ntn}}"           ← target tenant's NTN
#   "{{seller.business_name}}" ← target tenant's business_name
#   "{{seller.province}}"      ← target tenant's province
#   "{{seller.address}}"       ← target tenant's address (or "")
#
# Anything else in the payload (saleType, sroScheduleNo, item values,
# buyer block for end-consumer scenarios) is carried over verbatim —
# that's the whole point of the template.


_SELLER_TOKEN_FIELDS: dict[str, str] = {
    # PRAL wire field → attribute on Tenant
    "sellerNTNCNIC": "ntn",
    "sellerBusinessName": "business_name",
    "sellerProvince": "province",
    "sellerAddress": "address",
}


def _tokenize_seller_fields(payload: dict, seller: Tenant) -> dict:
    """Replace concrete seller values in `payload` with placeholder
    tokens like '{{seller.ntn}}'. Idempotent: tokens that already
    look like placeholders are left alone."""
    import copy
    result = copy.deepcopy(payload)
    for wire_field, attr in _SELLER_TOKEN_FIELDS.items():
        concrete = getattr(seller, attr, None) or ""
        token = f"{{{{seller.{attr}}}}}"
        if result.get(wire_field) == concrete and concrete:
            result[wire_field] = token
    return result


def _materialise_seller_fields(template_payload: dict, target: Tenant) -> dict:
    """Substitute '{{seller.X}}' tokens in `template_payload` with
    `target` tenant's concrete values. Returns the materialised dict
    ready to POST to PRAL."""
    import copy
    result = copy.deepcopy(template_payload)
    for wire_field, attr in _SELLER_TOKEN_FIELDS.items():
        token = f"{{{{seller.{attr}}}}}"
        if result.get(wire_field) == token:
            result[wire_field] = getattr(target, attr, None) or ""
    return result


def save_payload_as_template(
    *, name: str, scenario_code: str, payload: dict,
    seller_tenant: Tenant, created_by, notes: str = "",
) -> ScenarioPayloadTemplate:
    """Persist a working payload as a reusable template.

    Tokenises the seller block so the template can be applied to
    any future tenant without re-editing the seller fields.

    Use `update_or_create` on (name, scenario_code) so super-admin
    can update an existing template (e.g. "Wholesaler/Retailer — SN001")
    after a refinement.
    """
    tokenised = _tokenize_seller_fields(payload, seller_tenant)
    obj, _ = ScenarioPayloadTemplate.objects.update_or_create(
        name=name,
        scenario_code=scenario_code,
        defaults={
            "payload": tokenised,
            "notes": notes,
            "created_by": created_by,
        },
    )
    return obj


def apply_template_payload(
    template: ScenarioPayloadTemplate, target: Tenant,
) -> dict:
    """Return a payload ready to POST to PRAL for `target` tenant
    using the saved template. Does NOT contact PRAL; the caller
    chains this into run_single_scenario(payload_override=…) or
    similar to actually submit."""
    return _materialise_seller_fields(template.payload, target)
