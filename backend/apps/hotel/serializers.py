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
    """Body for POST /api/hotel/folios/ (open a stay).

    Pass `rooms` (list of room UUIDs) for a multi-room booking under one guest,
    or the single `room` field for backward compatibility. All rooms share the
    stay's check-in/out unless a future version sets them per room.
    """

    room = serializers.UUIDField(required=False)
    rooms = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False,
    )
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

    def validate(self, data):
        if not data.get("room") and not data.get("rooms"):
            raise serializers.ValidationError("Provide at least one room.")
        return data


class AddChargeSerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/{id}/charges/."""

    cart_lines = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    kind = serializers.ChoiceField(
        choices=["restaurant", "misc"], default="restaurant",
    )
    charge_date = serializers.DateField(required=False)
    # Optionally tag this charge to one of the folio's booked rooms.
    room = serializers.UUIDField(required=False, allow_null=True)
    client_uuid = serializers.UUIDField(required=False)
    terminal = serializers.UUIDField(required=False)


class CheckoutSerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/{id}/checkout/."""

    payments = serializers.ListField(child=serializers.DictField(), default=list)
    check_out = serializers.DateTimeField(required=False)


class UpdateStaySerializer(serializers.Serializer):
    """Body for PATCH /api/hotel/folios/{id}/ — edit an open stay.

    All fields optional; only provided ones change. Editing check_in/
    expected_check_out recomputes the room-night charges server-side.
    """

    guest_name = serializers.CharField(max_length=255, required=False)
    guest_cnic = serializers.CharField(max_length=20, required=False)
    guest_phone = serializers.CharField(max_length=20, required=False)
    guest_email = serializers.EmailField(required=False, allow_blank=True)
    guest_address = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    check_in = serializers.DateTimeField(required=False)
    expected_check_out = serializers.DateTimeField(required=False, allow_null=True)
    terminal = serializers.UUIDField(required=False)


class AddRoomSerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/{id}/rooms/ — add a room to a stay."""

    room = serializers.UUIDField()
    check_in = serializers.DateTimeField(required=False)
    expected_check_out = serializers.DateTimeField(required=False, allow_null=True)
    terminal = serializers.UUIDField(required=False)


class CancelStaySerializer(serializers.Serializer):
    """Body for POST /api/hotel/folios/{id}/cancel/."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")
