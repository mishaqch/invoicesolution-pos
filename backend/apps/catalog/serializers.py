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
    class Meta:
        model = UnitOfMeasure
        fields = ("code", "name_en", "name_ur", "is_decimal_quantity")


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
    class Meta:
        model = ProductBatch
        fields = (
            "id", "product", "batch_number", "manufactured_date", "expiry_date",
            "cost_price", "sale_price", "initial_quantity", "current_quantity",
            "branch", "created_at",
        )
        read_only_fields = ("id", "created_at")


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
            "reorder_level", "reorder_quantity",
            "is_serialized", "is_batch_tracked", "is_weighable", "has_variants",
            "image_url", "is_active",
            "created_at", "updated_at", "deleted_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "deleted_at")

    def validate(self, attrs):
        instance = self.instance
        sale_price = attrs.get("sale_price", instance.sale_price if instance else None)
        min_sale = attrs.get("min_sale_price", instance.min_sale_price if instance else None)
        if sale_price is not None and min_sale is not None and sale_price < min_sale:
            raise serializers.ValidationError(
                {"sale_price": "sale_price cannot be below min_sale_price."}
            )
        return attrs


class ProductPosSerializer(serializers.ModelSerializer):
    """Subset shipped to the POS terminal — strips cost_price."""

    class Meta:
        model = Product
        fields = (
            "id", "category",
            "name", "name_ur", "sku", "barcode",
            "uom", "tax_rate", "is_taxable",
            "sale_price", "retail_price", "min_sale_price", "max_discount_pct",
            "is_weighable", "image_url", "is_active",
            "updated_at", "deleted_at",
        )
