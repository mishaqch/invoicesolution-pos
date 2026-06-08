"""Stock movement helpers.

`record_movement()` writes a StockMovement *and* updates the corresponding
StockLevel, all inside a single DB transaction. This is the only sanctioned
way to mutate inventory. Direct StockLevel writes are still possible from
admin views (for opening balances), but the business logic should always go
through here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

from apps.catalog.models import Product, ProductBatch, ProductVariant
from apps.tenants.models import Branch

from ..models import StockLevel, StockMovement


@transaction.atomic
def record_movement(
    *,
    tenant_id,
    product: Product,
    branch: Branch,
    movement_type: str,
    quantity: Decimal,
    variant: Optional[ProductVariant] = None,
    batch: Optional[ProductBatch] = None,
    unit_cost: Optional[Decimal] = None,
    reference_type: Optional[str] = None,
    reference_id=None,
    reason: str = "",
    performed_by=None,
) -> StockMovement:
    """Append a movement and update the matching stock level."""
    movement = StockMovement.objects.create(
        tenant_id=tenant_id,
        product=product,
        variant=variant,
        batch=batch,
        branch=branch,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
        performed_by=performed_by,
    )
    level, _ = StockLevel.objects.select_for_update().get_or_create(
        tenant_id=tenant_id,
        product=product,
        variant=variant,
        branch=branch,
        defaults={"quantity": Decimal("0")},
    )
    level.quantity = (level.quantity or Decimal("0")) + quantity
    level.save(update_fields=["quantity", "updated_at"])

    # Batch-tracked goods (pharmacy): keep the batch's own running quantity in
    # step with the movement so FEFO picks the next batch once this one is
    # depleted, and the expiry list shows the true on-hand. The aggregate
    # StockLevel above is the sum across batches; the batch counter is per-lot.
    if batch is not None:
        batch_row = ProductBatch.objects.select_for_update().get(pk=batch.pk)
        batch_row.current_quantity = (batch_row.current_quantity or Decimal("0")) + quantity
        if batch_row.current_quantity < Decimal("0"):
            batch_row.current_quantity = Decimal("0")  # never go negative
        batch_row.save(update_fields=["current_quantity"])

    return movement
