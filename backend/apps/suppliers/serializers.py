from __future__ import annotations

from rest_framework import serializers

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            "id", "name", "contact_person", "phone", "email",
            "ntn", "strn", "address", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
