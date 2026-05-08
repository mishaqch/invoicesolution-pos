"""Stock transfer state machine.

draft → dispatched → received  (or → cancelled from draft only)

Each transition writes the appropriate stock_movements:
  - dispatch: one `transfer_out` per item against the from_branch
  - receive (with optional variances): one `transfer_in` per item against
    the to_branch using the actually-received quantity. If quantity_received
    differs from quantity_dispatched, an `adjustment_out` movement is
    appended to from_branch reconciling the variance (since we already
    deducted the dispatched amount).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import StockTransfer, StockTransferItem
from .movements import record_movement


@transaction.atomic
def dispatch(transfer: StockTransfer, *, dispatched_by=None) -> StockTransfer:
    if transfer.status != "draft":
        raise ValidationError({"status": f"Cannot dispatch from status '{transfer.status}'."})

    items = list(transfer.items.select_related("product", "variant"))
    if not items:
        raise ValidationError({"items": "Transfer has no items."})

    for item in items:
        record_movement(
            tenant_id=transfer.tenant_id,
            product=item.product,
            variant=item.variant,
            branch=transfer.from_branch,
            movement_type="transfer_out",
            quantity=Decimal("-1") * item.quantity_dispatched,
            reference_type="transfer",
            reference_id=transfer.id,
            performed_by=dispatched_by,
            reason=f"Transfer {transfer.transfer_number} dispatch",
        )

    transfer.status = "dispatched"
    transfer.dispatched_at = timezone.now()
    transfer.dispatched_by = dispatched_by
    transfer.save(update_fields=["status", "dispatched_at", "dispatched_by", "updated_at"])
    return transfer


@transaction.atomic
def receive(
    transfer: StockTransfer,
    counts: Iterable[tuple[str, Decimal]],
    *,
    received_by=None,
) -> StockTransfer:
    """Mark received with variance reconciliation.

    `counts` is an iterable of (item_id, quantity_received).
    """
    if transfer.status != "dispatched":
        raise ValidationError({"status": f"Cannot receive from status '{transfer.status}'."})

    counts_by_item = {str(item_id): Decimal(qty) for item_id, qty in counts}
    items = list(
        transfer.items.select_related("product", "variant")
    )

    for item in items:
        received_qty = counts_by_item.get(str(item.id), item.quantity_dispatched)
        variance = received_qty - item.quantity_dispatched

        record_movement(
            tenant_id=transfer.tenant_id,
            product=item.product,
            variant=item.variant,
            branch=transfer.to_branch,
            movement_type="transfer_in",
            quantity=received_qty,
            reference_type="transfer",
            reference_id=transfer.id,
            performed_by=received_by,
            reason=f"Transfer {transfer.transfer_number} receipt",
        )

        if variance:
            # Variance means stock evaporated (negative variance) or appeared
            # (positive). We reconcile against from_branch as an adjustment.
            record_movement(
                tenant_id=transfer.tenant_id,
                product=item.product,
                variant=item.variant,
                branch=transfer.from_branch,
                movement_type=(
                    "adjustment_out" if variance < 0 else "adjustment_in"
                ),
                quantity=variance,  # signed; subtracts from from_branch since
                                    # we already moved dispatched_qty out
                reference_type="transfer",
                reference_id=transfer.id,
                performed_by=received_by,
                reason=(
                    f"Transfer {transfer.transfer_number} variance reconciliation"
                ),
            )

        # Persist the actual variance on the line for reporting.
        StockTransferItem.objects.filter(pk=item.pk).update(
            quantity_received=received_qty,
            variance=variance,
        )

    transfer.status = "received"
    transfer.received_at = timezone.now()
    transfer.received_by = received_by
    transfer.save(update_fields=["status", "received_at", "received_by", "updated_at"])
    return transfer


@transaction.atomic
def cancel(transfer: StockTransfer) -> StockTransfer:
    if transfer.status != "draft":
        raise ValidationError(
            {"status": f"Cannot cancel from status '{transfer.status}'."}
        )
    transfer.status = "cancelled"
    transfer.save(update_fields=["status", "updated_at"])
    return transfer
