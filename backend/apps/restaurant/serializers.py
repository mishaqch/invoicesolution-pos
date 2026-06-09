from __future__ import annotations

from rest_framework import serializers

from .models import Modifier, ModifierGroup, Table


class TableSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Table
        fields = (
            "id", "branch", "branch_name", "name", "seats", "zone",
            "display_order", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modifier
        fields = ("id", "group", "name", "price_delta", "display_order", "is_active")
        read_only_fields = ("id",)


class ModifierGroupSerializer(serializers.ModelSerializer):
    modifiers = ModifierSerializer(many=True, read_only=True)

    class Meta:
        model = ModifierGroup
        fields = (
            "id", "name", "min_select", "max_select", "display_order",
            "is_active", "modifiers", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "modifiers")


class ModifierGroupWriteSerializer(serializers.ModelSerializer):
    """Create/update a group together with its options in one payload."""

    modifiers = ModifierSerializer(many=True, required=False)

    class Meta:
        model = ModifierGroup
        fields = ("id", "name", "min_select", "max_select", "display_order", "is_active", "modifiers")
        read_only_fields = ("id",)

    def create(self, validated_data):
        mods = validated_data.pop("modifiers", [])
        group = ModifierGroup.objects.create(**validated_data)
        for m in mods:
            Modifier.objects.create(group=group, **{k: v for k, v in m.items() if k != "group"})
        return group

    def update(self, instance, validated_data):
        mods = validated_data.pop("modifiers", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if mods is not None:
            instance.modifiers.all().delete()
            for m in mods:
                Modifier.objects.create(group=instance, **{k: v for k, v in m.items() if k != "group"})
        return instance
