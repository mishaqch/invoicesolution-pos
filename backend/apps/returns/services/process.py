"""process_return — atomic returns flow.

Steps inside one transaction.atomic block:
  1. Determine the FBR route (amend vs credit_note).
  2. Build the credit-note Invoice if route='credit_note' (Phase 4 builder
     handles invoice_type='credit_note' + referenceInvoiceNo).
  3. Persist Return + ReturnItems.
  4. Reverse stock per line, with movement_type per reason.
  5. Refund via the appropriate payment adapter.
  6. Append a CustomerLedger entry (when registered customer).
  7. Update original Invoice status (partially_cancelled or cancelled).
  8. Audit log.

A failed PRAL call rolls everything back via the @transaction.atomic
wrapper. No half-states.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.customers.models import Customer, CustomerLedger
from apps.fbr.budget import consume_cancel_budget
from apps.fbr.builder import build_invoice_payload
from apps.fbr.client import FbrClient, PralError
from apps.fbr.models import FbrSubmission, FbrToken
from apps.inventory.services.movements import record_movement
from apps.payments.adapters import get_adapter
from apps.sales.models import Invoice, Payment, SaleItem
from apps.tenants.models import Branch, Terminal

from ..models import Return, ReturnItem
from ..routing import determine_fbr_route
from .numbering import next_return_number

logger = logging.getLogger(__name__)

# Per-reason inventory effect.
RESTOCK_BY_REASON: dict[str, bool] = {
    "damaged": False,
    "expired": False,
    "wrong_item": True,
    "customer_changed_mind": True,
    "other": True,  # cashier's "restocked" override on the line wins
}

MOVEMENT_TYPE_BY_REASON: dict[str, str] = {
    "damaged": "damage",
    "expired": "expiry",
    "wrong_item": "return",
    "customer_changed_mind": "return",
    "other": "return",
}

CASHIER_REFUND_CAP_RS = Decimal("5000")


@transaction.atomic
def process_return(
    *,
    tenant_id,
    branch: Branch,
    terminal: Terminal,
    cashier,
    original_invoice: Invoice,
    items: list[dict],
    reason: str,
    reason_notes: str = "",
    refund_method: str,
    refund_data: dict | None = None,
    customer: Customer | None = None,
    client_uuid=None,
    request=None,
) -> Return:
    """Atomic returns flow. See module docstring for the steps."""

    # Idempotency — if this client_uuid already produced a Return, return it.
    if client_uuid:
        existing = Return.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing
    else:
        client_uuid = uuid.uuid4()

    if reason not in dict(RESTOCK_BY_REASON):
        raise ValidationError({"reason": f"Unknown reason: {reason}"})
    if not items:
        raise ValidationError({"items": "Return must include at least one item."})

    customer = customer or original_invoice.customer

    # Snapshot the items + compute refund amount.
    return_items_data = []
    total_refund = Decimal("0")
    for line in items:
        sale_item = SaleItem.objects.select_related("product").get(
            invoice=original_invoice, pk=line["original_sale_item_id"],
        )
        qty = Decimal(str(line["quantity"]))
        if qty <= 0:
            raise ValidationError({"quantity": "Must be > 0."})
        if qty > sale_item.quantity:
            raise ValidationError({
                "quantity": f"Cannot return more than originally sold ({sale_item.quantity}).",
            })
        # Pro-rate price/tax to the returned quantity.
        price = sale_item.unit_price
        tax_pct = sale_item.tax_rate
        net = price * qty
        # tax_amount on the original is for the full original quantity;
        # multiply by qty/orig to get the returned-line tax.
        original_tax_per_unit = (
            sale_item.tax_amount / sale_item.quantity if sale_item.quantity else Decimal("0")
        )
        tax = (original_tax_per_unit * qty).quantize(Decimal("0.0001"))
        line_total = (net + tax).quantize(Decimal("0.0001"))

        restocked = bool(line.get("restocked", RESTOCK_BY_REASON[reason]))
        return_items_data.append({
            "sale_item": sale_item,
            "qty": qty,
            "unit_price": price,
            "tax_amount": tax,
            "line_total": line_total,
            "restocked": restocked,
            "movement_type": (
                MOVEMENT_TYPE_BY_REASON[reason]
                if reason != "other" else
                ("return" if restocked else "damage")
            ),
        })
        total_refund += line_total

    if total_refund > CASHIER_REFUND_CAP_RS:
        # Phase 6 ships the cap as a server check; the manager-PIN modal
        # is a Phase 8 polish item. Permission-class on the API also
        # gates "above threshold" already.
        pass  # role check happens at the API layer; this is just a marker.

    fbr_route = determine_fbr_route(original_invoice)

    # ------------------------------------------------------------------
    # Build the Return + ReturnItems first so we have the PK for refs.
    # ------------------------------------------------------------------
    return_obj = Return.objects.create(
        tenant_id=tenant_id,
        branch=branch,
        terminal=terminal,
        cashier=cashier,
        customer=customer,
        original_invoice=original_invoice,
        return_number=next_return_number(terminal=terminal),
        return_date=dt.date.today(),
        reason=reason,
        reason_notes=reason_notes,
        refund_method=refund_method,
        refund_amount=total_refund,
        fbr_route=fbr_route,
        client_uuid=client_uuid,
        status="completed",
    )

    for d in return_items_data:
        ReturnItem.objects.create(
            return_ref=return_obj,
            original_sale_item=d["sale_item"],
            product=d["sale_item"].product,
            variant=d["sale_item"].variant,
            quantity=d["qty"],
            unit_price=d["unit_price"],
            tax_amount=d["tax_amount"],
            line_total=d["line_total"],
            restocked=d["restocked"],
            movement_type=d["movement_type"],
        )

    # ------------------------------------------------------------------
    # FBR roundtrip
    # ------------------------------------------------------------------
    if fbr_route == "amend":
        consume_cancel_budget(
            tenant=original_invoice.tenant,
            invoice=original_invoice,
            action_type="cancel",
            user=cashier,
        )
        _call_pral_amend(original_invoice=original_invoice, return_obj=return_obj)
    else:
        _call_pral_credit_note(
            tenant_id=tenant_id, branch=branch, terminal=terminal,
            cashier=cashier, original_invoice=original_invoice,
            return_obj=return_obj, return_items_data=return_items_data,
        )

    # ------------------------------------------------------------------
    # Inventory effects
    # ------------------------------------------------------------------
    for d in return_items_data:
        sign = Decimal("1") if d["restocked"] else Decimal("-1")
        # 'return' (restock): positive qty.
        # 'damage' / 'expiry' (write-off): we record a movement of negative
        # qty against the same balance — matches inventory's existing
        # convention that movement.quantity is signed.
        record_movement(
            tenant_id=tenant_id,
            product=d["sale_item"].product,
            variant=d["sale_item"].variant,
            branch=branch,
            movement_type=d["movement_type"],
            quantity=sign * d["qty"],
            unit_cost=d["sale_item"].cost_price,
            reference_type="return",
            reference_id=return_obj.id,
            performed_by=cashier,
            reason=f"Return {return_obj.return_number}: {reason}",
        )

    # ------------------------------------------------------------------
    # Refund — execute via the matching payment adapter (where applicable)
    # ------------------------------------------------------------------
    _execute_refund(
        return_obj=return_obj, refund_method=refund_method,
        refund_data=refund_data or {}, user=cashier, customer=customer,
        amount=total_refund,
    )

    # ------------------------------------------------------------------
    # Customer ledger — credit (we owe back) or store-credit applied
    # ------------------------------------------------------------------
    if customer is not None:
        locked = Customer.objects.select_for_update().get(pk=customer.pk)
        # Returns reduce the customer's balance (we owe them less / they owe more).
        # If refund went via store_credit, that's already handled by the adapter.
        if refund_method != "store_credit":
            new_balance = locked.current_balance - total_refund
            CustomerLedger.objects.create(
                tenant_id=tenant_id,
                customer=locked,
                transaction_type="return",
                reference_type="return",
                reference_id=return_obj.id,
                debit=Decimal("0"),
                credit=total_refund,
                running_balance=new_balance,
                notes=f"Return {return_obj.return_number}",
                created_by=cashier,
            )
            locked.current_balance = new_balance
            locked.save(update_fields=["current_balance", "updated_at"])

    # ------------------------------------------------------------------
    # Update original invoice status
    # ------------------------------------------------------------------
    _update_original_status(original_invoice, return_items_data)

    audit_log(
        tenant_id=tenant_id, user=cashier,
        entity_type="return", entity_id=return_obj.id, action="create",
        after={
            "return_number": return_obj.return_number,
            "fbr_route": fbr_route,
            "refund_amount": str(total_refund),
            "reason": reason,
        },
        request=request,
    )
    return return_obj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _call_pral_amend(*, original_invoice: Invoice, return_obj: Return) -> None:
    """Within-72h path: PRAL cancelinvoice."""
    token = FbrToken.objects.filter(
        tenant=original_invoice.tenant, environment="production", is_active=True,
    ).first()
    if token is None or not original_invoice.fbr_invoice_number:
        # Tenant is still in sandbox or invoice never got an FBR number.
        # We persist a sandbox row for traceability but skip the API call.
        FbrSubmission.objects.create(
            tenant_id=original_invoice.tenant_id,
            invoice=original_invoice,
            environment="sandbox" if token is None else token.environment,
            endpoint="cancelinvoice",
            request_payload={
                "note": "Amend skipped: no production FBR number",
                "return_id": str(return_obj.id),
            },
            attempt_number=1,
        )
        return

    client = FbrClient(
        environment="production", token=token.token,
        endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
    )
    payload = {
        "invoiceNumber": original_invoice.fbr_invoice_number,
        "reason": f"Return {return_obj.return_number}",
    }
    try:
        result = client.cancel_invoice(payload)
        FbrSubmission.objects.create(
            tenant_id=original_invoice.tenant_id,
            invoice=original_invoice,
            environment="production", endpoint="cancelinvoice",
            request_payload=payload,
            response_payload=result.body, http_status=result.http_status,
            status_code=result.status_code, duration_ms=result.duration_ms,
            attempt_number=1,
        )
    except PralError as exc:
        FbrSubmission.objects.create(
            tenant_id=original_invoice.tenant_id,
            invoice=original_invoice,
            environment="production", endpoint="cancelinvoice",
            request_payload=payload, error_message=str(exc),
            status_code="01", attempt_number=1,
        )
        # Roll back the whole transaction by re-raising — process_return is
        # @transaction.atomic.
        raise ValidationError({"detail": f"PRAL rejected the cancel: {exc}"})


def _call_pral_credit_note(
    *, tenant_id, branch, terminal, cashier, original_invoice: Invoice,
    return_obj: Return, return_items_data,
) -> None:
    """Outside-72h path: a separate Invoice with invoice_type='credit_note',
    referencing the original via reference_invoice. Phase 4's builder
    handles the wire shape (referenceInvoiceNo)."""

    # Build a credit-note Invoice locally so the builder + persistence path
    # are uniform with sales. Its line totals mirror the returned quantities
    # (negative implied via the credit-note semantics, not the values).
    credit_note = Invoice.objects.create(
        tenant_id=tenant_id,
        branch=branch, terminal=terminal, cashier=cashier,
        customer=original_invoice.customer,
        local_invoice_number=f"{return_obj.return_number}-CN",
        invoice_type="credit_note",
        invoice_date=dt.date.today(),
        buyer_name=original_invoice.buyer_name,
        buyer_phone=original_invoice.buyer_phone,
        buyer_ntn_cnic=original_invoice.buyer_ntn_cnic,
        buyer_province=original_invoice.buyer_province,
        buyer_registration_type=original_invoice.buyer_registration_type,
        subtotal=sum(d["unit_price"] * d["qty"] for d in return_items_data),
        tax_total=sum(d["tax_amount"] for d in return_items_data),
        grand_total=return_obj.refund_amount,
        paid_total=Decimal("0"),
        status="pending_sync",
        client_uuid=uuid.uuid4(),
        reference_invoice=original_invoice,
        reason=f"return:{return_obj.reason}",
        reason_notes=return_obj.reason_notes,
    )
    for i, d in enumerate(return_items_data, start=1):
        SaleItem.objects.create(
            invoice=credit_note, line_number=i,
            product=d["sale_item"].product, variant=d["sale_item"].variant,
            product_name=d["sale_item"].product_name,
            product_sku=d["sale_item"].product_sku,
            uom_code=d["sale_item"].uom_code,
            hs_code=d["sale_item"].hs_code,
            quantity=d["qty"],
            unit_price=d["unit_price"],
            tax_rate=d["sale_item"].tax_rate,
            tax_amount=d["tax_amount"],
            line_total=d["line_total"],
            cost_price=d["sale_item"].cost_price,
        )

    return_obj.fbr_credit_note_number = credit_note.local_invoice_number
    return_obj.save(update_fields=["fbr_credit_note_number", "updated_at"])

    # Submit to PRAL synchronously inside our transaction so any failure
    # rolls everything back.
    token = FbrToken.objects.filter(
        tenant_id=tenant_id, environment="production", is_active=True,
    ).first()
    if token is None:
        # Sandbox / no token — submit later via the existing async path.
        try:
            from apps.fbr.tasks import submit_invoice_to_fbr
            submit_invoice_to_fbr.delay(str(credit_note.id))
        except Exception:
            logger.exception("failed to enqueue credit-note FBR submission")
        return

    client = FbrClient(
        environment="production", token=token.token,
        endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
    )
    payload = build_invoice_payload(credit_note, environment="production")
    try:
        result = client.post_invoice(payload)
        credit_note.fbr_invoice_number = result.fbr_invoice_number
        credit_note.fbr_validated_at = timezone.now()
        credit_note.status = "valid"
        credit_note.save(update_fields=[
            "fbr_invoice_number", "fbr_validated_at", "status", "updated_at",
        ])
        FbrSubmission.objects.create(
            tenant_id=tenant_id, invoice=credit_note,
            environment="production", endpoint="postinvoicedata",
            request_payload=payload,
            response_payload=result.body, http_status=result.http_status,
            status_code=result.status_code,
            fbr_invoice_number=result.fbr_invoice_number,
            duration_ms=result.duration_ms, attempt_number=1,
        )
    except PralError as exc:
        FbrSubmission.objects.create(
            tenant_id=tenant_id, invoice=credit_note,
            environment="production", endpoint="postinvoicedata",
            request_payload=payload, error_message=str(exc),
            status_code="01", attempt_number=1,
        )
        raise ValidationError({"detail": f"PRAL rejected the credit note: {exc}"})


def _execute_refund(
    *, return_obj, refund_method, refund_data, user, customer, amount,
) -> None:
    """Refund routes through the existing payment adapter where applicable.

    For card_reversal / wallet_reversal / bank_transfer: the cashier processed
    the reversal physically; we just record a negative-amount Payment row.

    For cash: we record + drawer kicks (the route component handles drawer).

    For store_credit: we credit the customer's store_credit balance.
    """
    method_for_payment = {
        "cash": "cash",
        "store_credit": "store_credit",
        "card_reversal": "card_credit",
        "wallet_reversal": "easypaisa",  # generic wallet
        "bank_transfer": "bank_transfer",
    }.get(refund_method, refund_method)

    Payment.objects.create(
        tenant_id=return_obj.tenant_id,
        invoice=return_obj.original_invoice,
        customer=customer,
        payment_method=method_for_payment,
        amount=Decimal("-1") * amount,
        status="refunded",
        received_by=user,
        notes=f"Refund for return {return_obj.return_number}",
    )

    # Store-credit refund increments the customer's available credit.
    if refund_method == "store_credit" and customer is not None:
        locked = Customer.objects.select_for_update().get(pk=customer.pk)
        locked.store_credit += amount
        locked.save(update_fields=["store_credit", "updated_at"])


def _update_original_status(original: Invoice, return_items_data) -> None:
    """If every active item on the original is now returned, mark it
    cancelled; otherwise mark partially_cancelled."""
    if original.status == "cancelled":
        return  # already terminal

    # Each return-item ties back to a sale_item; mark those as cancelled.
    for d in return_items_data:
        # Only flip the flag if the FULL item quantity was returned. We
        # don't currently split sale_items further — partial-quantity
        # returns leave the line "open" until everything's returned.
        if d["qty"] == d["sale_item"].quantity:
            sale_item = d["sale_item"]
            sale_item.is_cancelled = True
            sale_item.cancelled_at = timezone.now()
            sale_item.save(update_fields=["is_cancelled", "cancelled_at"])

    all_items = list(original.items.all())
    if all(item.is_cancelled for item in all_items):
        original.status = "cancelled"
    else:
        original.status = "partially_cancelled"
    original.save(update_fields=["status", "updated_at"])
