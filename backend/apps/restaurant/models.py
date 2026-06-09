"""Restaurant / F&B domain.

Tables, menu modifiers (add-ons / sizes). Orders themselves are NOT a separate
model — an open order is an `is_held` sales.Invoice carrying order_type/table/
order_status (see sales.models.Invoice). This app only adds the supporting
reference data + the modifier catalog.

All tenant-scoped; user-facing rows soft-delete (deleted_at) per the
audit-don't-delete invariant.
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


class Table(TenantScopedModel):
    """A physical table a dine-in order is seated at."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    branch = models.ForeignKey(
        "tenants.Branch", on_delete=models.CASCADE, related_name="tables",
    )
    name = models.CharField(max_length=30)            # "T1", "Patio 4"
    seats = models.PositiveSmallIntegerField(default=4)
    zone = models.CharField(max_length=50, blank=True, null=True)  # "Ground", "Rooftop"
    display_order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "restaurant_tables"
        ordering = ["display_order", "name"]
        indexes = [models.Index(fields=["tenant", "branch"])]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_table_tenant_branch_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ModifierGroup(TenantScopedModel):
    """A set of options attached to menu items, e.g. "Size" or "Add-ons".

    `min_select`/`max_select` drive validation on the terminal: a required
    single-choice group (size) is min=1,max=1; optional add-ons is min=0,max=N.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    name = models.CharField(max_length=80)
    min_select = models.PositiveSmallIntegerField(default=0)
    max_select = models.PositiveSmallIntegerField(default=1)
    display_order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "restaurant_modifier_groups"
        ordering = ["display_order", "name"]
        indexes = [models.Index(fields=["tenant"])]

    def __str__(self) -> str:
        return self.name


class Modifier(models.Model):
    """One option within a group (e.g. "Large" +100, "Extra cheese" +50).

    Inherits the tenant of its group. price_delta is added to the line's unit
    price when chosen (DECIMAL, never float).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    group = models.ForeignKey(
        ModifierGroup, on_delete=models.CASCADE, related_name="modifiers",
    )
    name = models.CharField(max_length=80)
    price_delta = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "restaurant_modifiers"
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class MenuItemModifierGroup(models.Model):
    """Attaches a ModifierGroup to a menu item (catalog.Product). Many-to-many
    with an explicit through so we can order groups per product later."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="modifier_links",
    )
    group = models.ForeignKey(
        ModifierGroup, on_delete=models.CASCADE, related_name="product_links",
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "restaurant_menu_item_modifier_groups"
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "group"], name="uniq_menuitem_group",
            ),
        ]
