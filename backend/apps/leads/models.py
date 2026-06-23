"""Marketing-website leads.

A Lead is a contact request captured from the public invoicesolution.pk site
(the "Book a demo" / contact form). It is NOT tenant-scoped — these are people
who don't have an account yet. Stored in Postgres so a lead is never lost even
if the notification email fails to send.
"""

from __future__ import annotations

from django.db import models

from core.uuid7 import uuid7

PRODUCT_INTEREST = (
    ("pos", "POS Terminal"),
    ("digital_invoicing", "Digital Invoicing"),
    ("both", "Both"),
    ("", "Unspecified"),
)


class Lead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    name = models.CharField(max_length=120)
    business_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32)
    email = models.EmailField(max_length=254, blank=True)
    city = models.CharField(max_length=80, blank=True)
    business_type = models.CharField(max_length=80, blank=True)
    product_interest = models.CharField(
        max_length=20, choices=PRODUCT_INTEREST, blank=True, default=""
    )
    message = models.TextField(blank=True)

    # Provenance / triage.
    source = models.CharField(max_length=40, default="website")
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=400, blank=True)
    handled = models.BooleanField(
        default=False, help_text="Tick once a team member has followed up."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "leads"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["-created_at"], name="idx_lead_created"),
            models.Index(fields=["handled"], name="idx_lead_handled"),
        ]

    def __str__(self) -> str:
        return f"{self.business_name} ({self.name})"
