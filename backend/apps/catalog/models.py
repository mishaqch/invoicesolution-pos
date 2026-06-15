"""Catalog models — DATABASE_SCHEMA.md §3.

Two flavors of models live here:

  * Global lookups (no tenant_id): UnitOfMeasure, HsCode. Plain Model. Read-
    mostly. Seeded via a data migration (UoM) or management command (HsCode).
  * Tenant-scoped: TaxRate, Category, Product, ProductVariant, ProductBatch.
    Inherit from TenantScopedModel.

Postgres-specific indexes (gin full-text on products.name, partial expiry
index on product_batches) are added via RunSQL in the catalog initial
migration.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7

# ---------------------------------------------------------------------------
# Global lookups
# ---------------------------------------------------------------------------


class UnitOfMeasure(models.Model):
    code = models.CharField(max_length=20, primary_key=True)
    name_en = models.CharField(max_length=50)
    name_ur = models.CharField(max_length=50, blank=True, default="")
    is_decimal_quantity = models.BooleanField(default=False)

    class Meta:
        db_table = "units_of_measure"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.name_en})"


class HsCode(models.Model):
    code = models.CharField(max_length=15, primary_key=True)
    description = models.TextField()
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True
    )
    uom_default = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column="uom_default",
        related_name="hs_codes",
    )
    parent_code = models.CharField(max_length=15, blank=True, null=True)

    class Meta:
        db_table = "hs_codes"
        indexes = [
            models.Index(fields=["parent_code"], name="idx_hs_codes_parent"),
        ]

    def __str__(self) -> str:
        return f"{self.code}"


# ---------------------------------------------------------------------------
# Tenant-scoped
# ---------------------------------------------------------------------------


APPLIES_TO = (
    ("goods", "Goods"),
    ("services", "Services"),
    ("both", "Both"),
)


class TaxRate(TenantScopedModel):
    """Tenant-specific tax rates. Standard set seeded on tenant creation."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=50)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    is_compound = models.BooleanField(default=False)
    applies_to = models.CharField(max_length=20, choices=APPLIES_TO, default="goods")
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "tax_rates"
        indexes = [
            models.Index(fields=["tenant"], name="idx_tax_rates_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.rate}%)"


class Category(TenantScopedModel):
    """Hierarchical product category (self-referential parent)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="children",
    )
    name = models.CharField(max_length=255)
    name_ur = models.CharField(max_length=255, blank=True, default="")
    slug = models.SlugField(max_length=255)
    display_order = models.IntegerField(default=0)
    color = models.CharField(max_length=7, blank=True, null=True)  # hex
    icon = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="uniq_category_tenant_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant"],
                name="idx_categories_tenant",
                condition=models.Q(is_active=True),
            ),
            models.Index(fields=["parent"], name="idx_categories_parent"),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Forbid self-parenting and direct cycles. Deeper cycles are caught at save()."""
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError({"parent": "A category cannot be its own parent."})

    def save(self, *args, **kwargs):
        # Walk up the chain and refuse if we'd close a loop.
        if self.parent_id:
            visited: set[str] = set()
            current = self.parent
            while current is not None:
                if current.id == self.id or current.id in visited:
                    raise ValidationError({"parent": "Category hierarchy cannot contain a cycle."})
                visited.add(str(current.id))
                current = current.parent
        return super().save(*args, **kwargs)


class Product(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="products",
    )

    name = models.CharField(max_length=255)
    name_ur = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    sku = models.CharField(max_length=50)
    barcode = models.CharField(max_length=50, blank=True, null=True)

    hs_code = models.ForeignKey(
        HsCode,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column="hs_code",
    )
    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        db_column="uom_code",
        related_name="products",
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="products",
    )

    is_taxable = models.BooleanField(default=True)

    cost_price = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    sale_price = models.DecimalField(max_digits=14, decimal_places=4)
    retail_price = models.DecimalField(max_digits=14, decimal_places=4, blank=True, null=True)

    # Pakistan's 3rd Schedule (Sales Tax Act 1990): for these goods,
    # sales tax is charged on the printed retail price (MRP), not on
    # the actual sale value. Typical 3rd-Schedule items: refined sugar
    # (1701.9910), carbonated drinks, biscuits, cigarettes, mobile
    # phones, tea, infant milk, ice cream. PRAL enforces this on the
    # wire: invoices for these HS codes must carry
    # fixedNotifiedValueOrRetailPrice > 0 AND saleType="3rd Schedule
    # Goods" — otherwise rejected with error 0122. When this flag is
    # True, checkout snapshots retail_price → SaleItem.fixed_notified_value
    # and the FBR builder picks the retail-price saleType.
    is_third_schedule = models.BooleanField(
        default=False,
        help_text=(
            "Tick if this product is on Pakistan's 3rd Schedule "
            "(taxed on retail price, not sale price). Common 3rd-"
            "Schedule items: sugar, biscuits, carbonated drinks, "
            "cigarettes, mobile phones, tea. retail_price must be "
            "set when this is on."
        ),
    )

    # FBR sale type (PRAL transtypecode) — classifies how FBR taxes this item
    # on the invoice. Verbatim PRAL string (see apps.fbr.sale_types). Flows to
    # SaleItem.sale_type → the invoice payload's "saleType". `is_third_schedule`
    # stays the mechanical flag that drives retail-price snapshotting; selecting
    # the "3rd Schedule Goods" sale type forces is_third_schedule on (see
    # ProductSerializer.validate). Default = standard rate, so existing products
    # are unchanged.
    sale_type = models.CharField(
        max_length=50,
        default="Goods at standard rate (default)",
        help_text=(
            "How FBR taxes this item (Standard, 3rd Schedule, Reduced, "
            "Zero-rated, Exempt, Electric Vehicle, …). Must match PRAL's "
            "transtypecode list exactly; pick from the dropdown."
        ),
    )

    # FBR SRO reference — required for reduced-rate (8th Schedule) and some
    # exempt/zero lines: PRAL needs the schedule name + the item's serial within
    # that schedule, or it rejects the line. e.g. reduced-rate 1% goods send
    # sroScheduleNo="EIGHTH SCHEDULE Table 1" + sroItemSerialNo="70". Snapshotted
    # onto SaleItem at checkout. Blank for ordinary standard-rate goods.
    sro_schedule_no = models.CharField(
        max_length=50, blank=True, default="",
        help_text='FBR SRO schedule, e.g. "EIGHTH SCHEDULE Table 1". Needed for reduced-rate goods.',
    )
    sro_item_serial_no = models.CharField(
        max_length=20, blank=True, default="",
        help_text="The item's serial number within that SRO schedule, e.g. 70.",
    )

    min_sale_price = models.DecimalField(max_digits=14, decimal_places=4, blank=True, null=True)
    max_discount_pct = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    reorder_level = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    reorder_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )

    is_serialized = models.BooleanField(default=False)
    is_batch_tracked = models.BooleanField(default=False)
    is_weighable = models.BooleanField(default=False)
    has_variants = models.BooleanField(default=False)

    image_url = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_products",
    )

    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "products"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                name="uniq_product_tenant_sku",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant"],
                name="idx_products_tenant",
                condition=models.Q(deleted_at__isnull=True, is_active=True),
            ),
            models.Index(
                fields=["tenant", "barcode"],
                name="idx_products_barcode",
                condition=models.Q(barcode__isnull=False),
            ),
            models.Index(fields=["category"], name="idx_products_category"),
            # gin full-text index added via RunSQL in the migration
            # (Django's Index doesn't compose with to_tsvector directly).
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"

    def clean(self) -> None:
        if self.min_sale_price is not None and self.sale_price < self.min_sale_price:
            raise ValidationError(
                {"sale_price": "sale_price cannot be below min_sale_price."}
            )


class ProductVariant(models.Model):
    """For products like clothing (size × color). Inherits the tenant of its product."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=50)
    barcode = models.CharField(max_length=50, blank=True, null=True)
    attributes = models.JSONField(default=dict)
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    sale_price = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_variants"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "sku"],
                name="uniq_variant_product_sku",
            ),
        ]


class ProductBatch(models.Model):
    """For pharma + date-sensitive goods. Inherits the tenant of its product."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="batches",
    )
    batch_number = models.CharField(max_length=50)
    manufactured_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    sale_price = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True
    )
    initial_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    current_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="batches",
    )
    # Traceability: which supplier this batch came from (set by a goods
    # receipt). Nullable — batches added manually have no supplier.
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_batches"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "batch_number", "branch"],
                name="uniq_batch_product_batchno_branch",
            ),
        ]
