"""Stock audit finalization.

Finalizing an audit appends one `adjustment_in`/`adjustment_out` movement
per line whose variance != 0, then flips the audit to 'finalized'.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import StockAudit
from .movements import record_movement


@transaction.atomic
def finalize(audit: StockAudit, *, performed_by=None) -> StockAudit:
    if audit.status != "in_progress":
        raise ValidationError({"status": f"Cannot finalize from status '{audit.status}'."})

    for item in audit.items.select_related("product", "variant"):
        if item.variance and item.variance != Decimal("0"):
            record_movement(
                tenant_id=audit.tenant_id,
                product=item.product,
                variant=item.variant,
                branch=audit.branch,
                movement_type=(
                    "adjustment_out" if item.variance < 0 else "adjustment_in"
                ),
                quantity=item.variance,  # signed
                reference_type="audit",
                reference_id=audit.id,
                performed_by=performed_by,
                reason=item.variance_reason or f"Audit {audit.audit_number} reconciliation",
            )

    audit.status = "finalized"
    audit.finalized_at = timezone.now()
    audit.save(update_fields=["status", "finalized_at", "updated_at"])
    return audit
