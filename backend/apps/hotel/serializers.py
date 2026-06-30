from __future__ import annotations

from rest_framework import serializers

from .models import GuestFolio, Room


class RoomSerializer(serializers.ModelSerializer):
    nightly_total = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True,
    )

    class Meta:
        model = Room
        fields = (
            "id", "branch", "room_number", "room_type",
            "nightly_base", "nightly_tax", "nightly_total",
            "product", "display_order", "status", "is_active",
        )
        read_only_fields = ("id", "status")


class FolioListSerializer(serializers.ModelSerializer):
    """Light row for the open-stays list."""

    room_number = serializers.CharField(source="room.room_number", read_only=True, default=None)
    room_type = serializers.CharField(source="room.room_type", read_only=True, default=None)

    class Meta:
        model = GuestFolio
        fields = (
            "id", "folio_number", "guest_name", "guest_phone",
            "room", "room_number", "room_type",
            "check_in", "expected_check_out", "check_out", "nights", "status",
            "created_at",
        )


class OpenStaySerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/ (open a stay)."""

    room = serializers.UUIDField()
    guest_name = serializers.CharField(max_length=255)
    guest_cnic = serializers.CharField(max_length=20)
    guest_phone = serializers.CharField(max_length=20)
    guest_email = serializers.EmailField(required=False, allow_blank=True, default="")
    guest_address = serializers.CharField(required=False, allow_blank=True, default="")
    check_in = serializers.DateTimeField(required=False)
    expected_check_out = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    # Optional terminal context (falls back to implicit defaults server-side).
    terminal = serializers.UUIDField(required=False)


class AddChargeSerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/{id}/charges/."""

    cart_lines = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    kind = serializers.ChoiceField(
        choices=["restaurant", "misc"], default="restaurant",
    )
    charge_date = serializers.DateField(required=False)
    client_uuid = serializers.UUIDField(required=False)
    terminal = serializers.UUIDField(required=False)


class CheckoutSerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/{id}/checkout/."""

    payments = serializers.ListField(child=serializers.DictField(), default=list)
    check_out = serializers.DateTimeField(required=False)
