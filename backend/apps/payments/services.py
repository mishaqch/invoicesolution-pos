"""Payment-method orchestration outside the per-tender hot path.

Phase 5 ships:
  - mark_cheque_cleared / mark_cheque_bounced
  - the API view delegates to these
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.services import log as audit_log
from apps.notifications.services import notify
from apps.sales.models import Payment


@transaction.atomic
def mark_cheque_cleared(payment: Payment, *, user=None, request=None) -> Payment:
    if payment.payment_method != "cheque":
        raise ValidationError({"payment_method": "Not a cheque."})
    if payment.cheque_status != "pending":
        raise ValidationError({"cheque_status": f"Cheque is {payment.cheque_status}."})
    payment.cheque_status = "cleared"
    payment.save(update_fields=["cheque_status", "updated_at"])
    audit_log(
        tenant_id=payment.tenant_id, user=user,
        entity_type="payment", entity_id=payment.id, action="cheque_cleared",
        request=request,
    )
    return payment


@transaction.atomic
def mark_cheque_bounced(
    payment: Payment, *, reason: str = "", user=None, request=None,
) -> Payment:
    if payment.payment_method != "cheque":
        raise ValidationError({"payment_method": "Not a cheque."})
    if payment.cheque_status != "pending":
        raise ValidationError({"cheque_status": f"Cheque is {payment.cheque_status}."})

    payment.cheque_status = "bounced"
    payment.status = "failed"
    payment.notes = (payment.notes or "") + f"\n[Bounced] {reason}".strip()
    payment.save(update_fields=["cheque_status", "status", "notes", "updated_at"])

    # Flag the customer (notes append) so the next admin sees it.
    if payment.customer_id:
        from apps.customers.models import Customer
        cust = Customer.objects.select_for_update().get(pk=payment.customer_id)
        flag = (
            f"\n[{payment.cheque_date}] Cheque {payment.cheque_number} from "
            f"{payment.bank_name or 'unknown bank'} bounced. "
            f"Reason: {reason or 'not given'}."
        )
        cust.notes = (cust.notes or "") + flag
        cust.save(update_fields=["notes", "updated_at"])

    notify(
        tenant_id=payment.tenant_id,
        notification_type="payment.cheque_bounced",
        title=f"Cheque bounced: {payment.cheque_number or payment.id}",
        message=(
            f"Bank: {payment.bank_name or 'unknown'}. "
            f"Customer flagged. Reason: {reason or 'not given'}."
        ),
        severity="danger",
        data={"payment_id": str(payment.id)},
    )
    audit_log(
        tenant_id=payment.tenant_id, user=user,
        entity_type="payment", entity_id=payment.id, action="cheque_bounced",
        after={"reason": reason}, request=request,
    )
    return payment
