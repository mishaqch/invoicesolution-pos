"""Catalog DRF serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    Category,
    HsCode,
    Product,
    ProductBatch,
    ProductVariant,
    TaxRate,
    UnitOfMeasure,
)


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    # The exact unit string FBR/PRAL accepts for this code (e.g. PCS/BOX/TIN
    # all → "Numbers, pieces, units"). Single source of truth: fbr.builder.
    # The product form groups the dropdown by this so each FBR unit appears
    # once. `fbr_uom_label` is the friendly DISPLAY text (e.g. "Kilogram" for
    # the "KG" FBR unit) — presentation only; submission always uses fbr_uom.
    fbr_uom = serializers.SerializerMethodField()
    fbr_uom_label = serializers.SerializerMethodField()

    class Meta:
        model = UnitOfMeasure
        fields = (
            "code", "name_en", "name_ur", "is_decimal_quantity",
            "fbr_uom", "fbr_uom_label",
        )

    def get_fbr_uom(self, obj) -> str:
        from apps.fbr.builder import map_uom
        return map_uom(obj.code)

    def get_fbr_uom_label(self, obj) -> str:
        from apps.fbr.builder import uom_display_label
        return uom_display_label(obj.code)


class HsCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HsCode
        fields = ("code", "description", "default_tax_rate", "uom_default", "parent_code")


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = (
            "id", "name", "rate", "is_compound", "applies_to", "is_default",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "id", "parent", "name", "name_ur", "slug",
            "display_order", "color", "icon", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = (
            "id", "product", "sku", "barcode", "attributes",
            "cost_price", "sale_price", "is_active",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ProductBatchSerializer(serializers.ModelSerializer):
    # Read-only convenience fields for the batch list UI.
    product_name = serializers.CharField(source="product.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = ProductBatch
        fields = (
            "id", "product", "product_name", "batch_number",
            "manufactured_date", "expiry_date",
            "cost_price", "sale_price", "initial_quantity", "current_quantity",
            "branch", "branch_name", "created_at",
        )
        # current_quantity is derived from initial_quantity on create and is
        # only ever changed afterwards via stock movements — never edited
        # directly through this serializer.
        read_only_fields = ("id", "created_at", "current_quantity")


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            "id", "category",
            "name", "name_ur", "description",
            "sku", "barcode",
            "hs_code", "uom", "tax_rate", "is_taxable",
            "cost_price", "sale_price", "retail_price",
            "min_sale_price", "max_discount_pct",
            "is_third_schedule", "sale_type", "sro_schedule_no", "sro_item_serial_no",
            "reorder_level", "reorder_quantity",
            "is_serialized", "is_batch_tracked", "is_weighable", "has_variants",
            "image_url", "is_active",
            "created_at", "updated_at", "deleted_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "deleted_at")

    def validate(self, attrs):
        from apps.fbr.sale_types import is_valid_sale_type

        instance = self.instance
        # Friendly SKU-uniqueness check (per tenant, LIVE products only) so a
        # duplicate SKU returns a clean 400 instead of crashing with a 500 from
        # the DB unique constraint. Soft-deleted products don't count — their
        # SKU is free to reuse.
        sku = attrs.get("sku", instance.sku if instance else None)
        request = self.context.get("request")
        tenant_id = getattr(request, "tenant_id", None) if request else None
        if sku and tenant_id:
            dupe = Product.objects.filter(
                tenant_id=tenant_id, sku=sku, deleted_at__isnull=True,
            )
            if instance is not None:
                dupe = dupe.exclude(pk=instance.pk)
            if dupe.exists():
                raise serializers.ValidationError({
                    "sku": f"A product with SKU '{sku}' already exists. Use a different SKU."
                })

        sale_price = attrs.get("sale_price", instance.sale_price if instance else None)
        min_sale = attrs.get("min_sale_price", instance.min_sale_price if instance else None)
        if sale_price is not None and min_sale is not None and sale_price < min_sale:
            raise serializers.ValidationError(
                {"sale_price": "sale_price cannot be below min_sale_price."}
            )
        # Sale type must be a real PRAL transtypecode (defends the wire format —
        # a bad string would be rejected with errorCode 0204).
        sale_type = attrs.get(
            "sale_type", instance.sale_type if instance else None,
        )
        if sale_type is not None and not is_valid_sale_type(sale_type):
            raise serializers.ValidationError({
                "sale_type": "Unknown FBR sale type. Pick one from /catalog/sale-types/."
            })
        # The "3rd Schedule Goods" sale type implies 3rd-Schedule handling
        # (retail-price taxation), so keep the mechanical flag in sync — this is
        # what drives the retail_price snapshot at checkout + the check below.
        if sale_type == "3rd Schedule Goods":
            attrs["is_third_schedule"] = True
        # 3rd-Schedule items must have a retail_price set — PRAL
        # rejects the invoice line otherwise (errorCode 0122).
        is_third = attrs.get(
            "is_third_schedule",
            instance.is_third_schedule if instance else False,
        )
        retail = attrs.get(
            "retail_price",
            instance.retail_price if instance else None,
        )
        if is_third and (retail is None or retail <= 0):
            raise serializers.ValidationError({
                "retail_price":
                    "retail_price is required and must be > 0 when "
                    "is_third_schedule is on. PRAL charges tax on the "
                    "printed retail price for 3rd-Schedule goods (sugar, "
                    "biscuits, etc.); without it, the invoice line is "
                    "rejected with errorCode 0122."
            })
        # HS code is required: every invoice line submitted to PRAL
        # carries the hsCode field, and our SaleItem snapshots it from
        # the parent Product at sale time. A product without an HS code
        # would produce an invoice PRAL rejects with errorCode 0052.
        # The Product.hs_code FK is `null=True` at the DB level for
        # backwards compatibility with old rows; enforce at the API
        # boundary instead.
        hs_code = attrs.get("hs_code", instance.hs_code if instance else None)
        if hs_code is None:
            raise serializers.ValidationError({
                "hs_code":
                    "HS code is required. Every product line submitted "
                    "to FBR must carry a valid HS code from PRAL's "
                    "catalog. Pick one from /catalog/hs-codes."
            })
        return attrs


class ProductPosSerializer(serializers.ModelSerializer):
    """Subset shipped to the POS terminal — strips cost_price."""

    class Meta:
        model = Product
        fields = (
            "id", "category",
            "name", "name_ur", "sku", "barcode",
            # hs_code FK PK IS the code string (e.g. "2402.2000"). The terminal
            # needs it so a sale rung by SCANNING carries a valid HS code to
            # FBR — without it, scanned-sale fiscalization is rejected.
            "uom", "tax_rate", "hs_code", "is_taxable",
            "sale_price", "retail_price", "min_sale_price", "max_discount_pct",
            "is_third_schedule", "sale_type", "sro_schedule_no", "sro_item_serial_no",
            # is_batch_tracked tells the terminal a sale of this product must be
            # rung against a specific batch (FEFO) so expiry-sensitive stock is
            # depleted nearest-expiry-first.
            "is_batch_tracked",
            "is_weighable", "image_url", "is_active",
            "updated_at", "deleted_at",
        )


class ProductBatchPosSerializer(serializers.ModelSerializer):
    """Batches shipped to the POS terminal for FEFO selection at sale time."""

    class Meta:
        model = ProductBatch
        fields = (
            "id", "product", "batch_number", "expiry_date",
            "current_quantity", "branch",
        )
