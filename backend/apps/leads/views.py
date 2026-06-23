"""Public lead-capture endpoint for the marketing site.

POST /api/leads/ — AllowAny, throttled, honeypot-protected. Persists the lead
to Postgres first (so it's never lost), THEN tries to email the team. An email
failure is logged but never fails the request — the DB row + super-admin list
is the authoritative inbox.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Lead
from .serializers import LeadSerializer

logger = logging.getLogger(__name__)


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LeadCreateView(APIView):
    """Create a lead from the public contact / book-a-demo form."""

    permission_classes = [AllowAny]
    authentication_classes: list = []  # public form — no auth header expected
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "leads"

    def post(self, request):
        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        # Honeypot: a hidden field real users never see. If a bot filled it,
        # pretend success (201) but DON'T persist or email — spam dead-ends.
        if (data.pop("company_website", "") or "").strip():
            logger.info("leads: honeypot tripped, dropping spam submission")
            return Response(
                {"detail": "Thanks! We'll be in touch shortly."},
                status=status.HTTP_201_CREATED,
            )

        lead = Lead.objects.create(
            **data,
            source="website",
            ip=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:400],
        )

        self._notify(lead)

        return Response(
            {"detail": "Thanks! We'll be in touch shortly.", "id": str(lead.id)},
            status=status.HTTP_201_CREATED,
        )

    def _notify(self, lead: Lead) -> None:
        """Email the team. Never raises — a send failure must not lose the lead."""
        recipients = getattr(settings, "LEADS_NOTIFY_EMAILS", []) or []
        if not recipients:
            logger.info("leads: new lead %s (no LEADS_NOTIFY_EMAILS set, DB only)", lead.id)
            return
        interest = dict(Lead._meta.get_field("product_interest").choices).get(
            lead.product_interest, lead.product_interest or "—"
        )
        body = (
            f"New lead from invoicesolution.pk\n\n"
            f"Business:  {lead.business_name}\n"
            f"Name:      {lead.name}\n"
            f"Phone:     {lead.phone}\n"
            f"Email:     {lead.email or '—'}\n"
            f"City:      {lead.city or '—'}\n"
            f"Type:      {lead.business_type or '—'}\n"
            f"Interest:  {interest}\n"
            f"Message:   {lead.message or '—'}\n\n"
            f"Received:  {lead.created_at:%Y-%m-%d %H:%M %Z}\n"
        )
        try:
            send_mail(
                subject=f"New lead — {lead.business_name}",
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=recipients,
                fail_silently=False,
            )
        except Exception:  # noqa: BLE001 — never break the request on email
            logger.exception("leads: failed to email notification for lead %s", lead.id)
