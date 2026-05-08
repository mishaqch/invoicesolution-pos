"""Inventory signals — early-warning guard against modifying stock_movements.

The DB grants are the actual enforcement; this signal just makes mistakes
visible immediately in tests + dev where the dev role often has full
privileges. In production the REVOKE migration ensures even raw SQL fails.
"""

from __future__ import annotations

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import StockMovement


class StockMovementImmutableError(PermissionError):
    """Raised when something tries to UPDATE or DELETE a stock_movements row."""


@receiver(pre_save, sender=StockMovement)
def block_stock_movement_update(sender, instance: StockMovement, **kwargs):
    # `update_fields=None` + existing pk → it's an update.
    if instance.pk is not None and StockMovement.objects.filter(pk=instance.pk).exists():
        raise StockMovementImmutableError(
            "stock_movements is append-only. Insert a new row to reverse a movement."
        )


@receiver(pre_delete, sender=StockMovement)
def block_stock_movement_delete(sender, instance: StockMovement, **kwargs):
    raise StockMovementImmutableError(
        "stock_movements is append-only. Delete is forbidden."
    )


# Touch post_save so flake8 is happy with the import — and so signal wiring
# verifies on app load.
@receiver(post_save, sender=StockMovement)
def _noop(sender, **kwargs):
    return None
