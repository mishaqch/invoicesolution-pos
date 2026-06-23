from __future__ import annotations

from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    """Validates a public lead submission.

    `company_website` is a write-only HONEYPOT — a hidden field the real form
    keeps empty. Bots that auto-fill every field will populate it; we reject
    those silently-but-validly (see the view) so spam never reaches the DB or
    inbox. `source`, `ip`, `user_agent` are server-set, never client-trusted.
    """

    company_website = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )

    class Meta:
        model = Lead
        fields = (
            "id",
            "name",
            "business_name",
            "phone",
            "email",
            "city",
            "business_type",
            "product_interest",
            "message",
            "company_website",
            "created_at",
        )
        read_only_fields = ("id", "created_at")
        extra_kwargs = {
            # Required for a usable lead; the rest are optional.
            "name": {"required": True, "allow_blank": False},
            "business_name": {"required": True, "allow_blank": False},
            "phone": {"required": True, "allow_blank": False},
            "email": {"required": False, "allow_blank": True},
        }

    def validate_phone(self, value: str) -> str:
        digits = [c for c in value if c.isdigit()]
        if len(digits) < 7:
            raise serializers.ValidationError("Enter a valid phone number.")
        return value.strip()
