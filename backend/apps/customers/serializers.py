from rest_framework import serializers

from .models import Customer, CustomerGroup, CustomerLedger


class CustomerGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerGroup
        fields = ("id", "name", "default_discount_pct", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "id", "group", "customer_code",
            "name", "phone", "email", "cnic", "ntn",
            "registration_type", "province", "address", "date_of_birth",
            "credit_limit", "current_balance", "store_credit", "loyalty_points",
            "is_active", "notes",
            "created_at", "updated_at", "deleted_at",
        )
        read_only_fields = (
            "id", "current_balance", "store_credit", "loyalty_points",
            "created_at", "updated_at", "deleted_at",
        )


class CustomerLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerLedger
        fields = (
            "id", "customer",
            "transaction_type", "reference_type", "reference_id",
            "debit", "credit", "running_balance",
            "notes", "created_by", "created_at",
        )
        read_only_fields = fields
