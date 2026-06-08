from __future__ import annotations

from rest_framework import serializers

from .models import GoodsReceipt, GoodsReceiptItem


class GoodsReceiptItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = GoodsReceiptItem
        fields = (
            "id", "product", "product_name", "quantity", "cost_price",
            "batch_number", "manufactured_date", "expiry_date", "batch",
        )
        read_only_fields = ("id", "batch", "product_name")


class GoodsReceiptSerializer(serializers.ModelSerializer):
    items = GoodsReceiptItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = (
            "id", "supplier", "supplier_name", "branch", "branch_name",
            "reference", "received_date", "status", "notes",
            "posted_at", "created_at", "items",
        )
        read_only_fields = ("id", "status", "posted_at", "created_at")

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        receipt = GoodsReceipt.objects.create(**validated_data)
        for item in items:
            GoodsReceiptItem.objects.create(receipt=receipt, **item)
        return receipt

    def update(self, instance, validated_data):
        if instance.status == "posted":
            raise serializers.ValidationError("A posted goods receipt cannot be edited.")
        items = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for item in items:
                GoodsReceiptItem.objects.create(receipt=instance, **item)
        return instance
