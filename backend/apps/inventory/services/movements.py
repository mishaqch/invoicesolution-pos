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

from ..models import StockLevel, StockMovement, Warehouse


@transaction.atomic
def record_movement(
    *,
    tenant_id,
    product: Product,
    branch: Branch,
    movement_type: str,
    quantity: Decimal,
    warehouse: Optional[Warehouse] = None,
    variant: Optional[ProductVariant] = None,
    batch: Optional[ProductBatch] = None,
    unit_cost: Optional[Decimal] = None,
    reference_type: Optional[str] = None,
    reference_id=None,
    reason: str = "",
    performed_by=None,
) -> StockMovement:
    """Append a movement and update the matching stock level.

    `warehouse` is optional and defaults to None. When None (every POS / legacy
    caller), the stock level is keyed by (product, variant, branch) with a NULL
    warehouse — identical to the pre-warehouse behaviour. When set (Digital
    Invoicing), the level is keyed by (product, variant, warehouse) instead, so
    a branch's godowns track stock independently.
    """
    movement = StockMovement.objects.create(
        tenant_id=tenant_id,
        product=product,
        variant=variant,
        batch=batch,
        branch=branch,
        warehouse=warehouse,
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
        warehouse=warehouse,
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


# Movement types that BRING stock in — these can start a stock run, so the
# "opening" of the current run is the balance right after the first of them.
# (A `sale`/`return`/`damage` can't *start* a positive run on its own.)
_RUN_STARTERS = frozenset(
    {"opening_balance", "adjustment_in", "purchase", "transfer_in"}
)


def compute_opening(movements) -> Optional[Decimal]:
    """The on-hand a stock line OPENED with for its CURRENT run.

    `movements` is an iterable of objects with `.movement_type` and `.quantity`
    in CHRONOLOGICAL order (oldest first), all for the same product + location.

    "Opening of the current run" = the balance immediately after the first
    stock-IN movement that began the stock you hold today — i.e. after the most
    recent time the running balance rose from <= 0 up to a positive value via a
    stock-in. This is the number a shopkeeper means by "what did I start with":

      - CRUISE: first move is adjustment_in 200  -> opening = 200
      - EV(typo): opening_balance 234234, then set to 0, then re-stocked 500 and
        sold to 498 -> opening = 500 (the run that's actually on the shelf now),
        NOT the long-since-reversed 234234 typo.

    Returns None when no stock-in has ever started a positive run (e.g. a line
    that only ever went negative from sales with no stock-in) — the caller
    renders that as "—".
    """
    moves = list(movements)
    if not moves:
        return None

    # Walk forward tracking the running balance. Each time the balance crosses
    # from <= 0 up to positive via a run-starter, that's a NEW run opening; we
    # remember the latest such opening, so reversed/abandoned runs are dropped.
    running = Decimal("0")
    opening: Optional[Decimal] = None
    for m in moves:
        prev = running
        qty = m.quantity or Decimal("0")
        running = running + qty
        if (
            m.movement_type in _RUN_STARTERS
            and prev <= Decimal("0")
            and running > Decimal("0")
        ):
            opening = running
    return opening
