"""Goods-receipt posting.

`post_receipt` turns a draft GRN into actual stock: for each line it creates (or
tops up) a ProductBatch for batch-tracked products, then records a `purchase`
stock movement via record_movement — the single sanctioned stock mutation, which
keeps StockLevel, the batch's current_quantity, and the audit ledger consistent.

Idempotent-ish: re-posting a posted receipt is rejected (the stock already
moved), so a double-submit can't double-count.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductBatch
from apps.inventory.services.movements import record_movement

from .models import GoodsReceipt


@transaction.atomic
def post_receipt(receipt: GoodsReceipt, *, user=None) -> GoodsReceipt:
    if receipt.status == "posted":
        raise ValidationError("This goods receipt has already been posted.")

    items = list(receipt.items.select_related("product").all())
    if not items:
        raise ValidationError("Add at least one line before posting.")

    for item in items:
        qty = Decimal(str(item.quantity))
        if qty <= 0:
            raise ValidationError("Each line quantity must be greater than zero.")

        batch = None
        if item.product.is_batch_tracked:
            if not item.batch_number:
                raise ValidationError(
                    f"{item.product.name} is batch-tracked — a batch number is required."
                )
            # Top up an existing batch (same product/number/branch) or create one.
            batch, created = ProductBatch.objects.select_for_update().get_or_create(
                product=item.product,
                batch_number=item.batch_number,
                branch=receipt.branch,
                defaults={
                    "manufactured_date": item.manufactured_date,
                    "expiry_date": item.expiry_date,
                    "cost_price": item.cost_price,
                    "supplier": receipt.supplier,
                    "initial_quantity": Decimal("0"),
                    "current_quantity": Decimal("0"),
                },
            )
            if not created:
                # Keep expiry/supplier fresh from the latest receipt.
                batch.expiry_date = item.expiry_date or batch.expiry_date
                batch.supplier = receipt.supplier
                if item.cost_price is not None:
                    batch.cost_price = item.cost_price
                batch.save(update_fields=["expiry_date", "supplier", "cost_price"])
            item.batch = batch
            item.save(update_fields=["batch"])

        # record_movement bumps StockLevel AND (when batch is set) the batch's
        # current_quantity — single source of truth for stock.
        record_movement(
            tenant_id=receipt.tenant_id,
            product=item.product,
            branch=receipt.branch,
            batch=batch,
            movement_type="purchase",
            quantity=qty,
            unit_cost=item.cost_price,
            reference_type="goods_receipt",
            reference_id=receipt.id,
            reason=f"GRN {receipt.reference or receipt.id}",
            performed_by=user,
        )

    receipt.status = "posted"
    receipt.posted_at = timezone.now()
    receipt.save(update_fields=["status", "posted_at", "updated_at"])
    return receipt
