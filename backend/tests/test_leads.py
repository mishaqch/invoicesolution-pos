"""Public marketing-site lead capture (/api/leads/).

The endpoint is AllowAny + throttled + honeypot-protected. It must:
  - persist a valid lead to the DB and return 201,
  - reject missing required fields with 400,
  - silently drop honeypot (bot) submissions WITHOUT creating a row,
  - email the team when LEADS_NOTIFY_EMAILS is set (locmem backend),
  - never fail the request if email sending raises.
"""

from __future__ import annotations

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.leads.models import Lead

pytestmark = pytest.mark.django_db


def _payload(**over):
    base = {
        "name": "Ahmed Khan",
        "business_name": "Khan Super Store",
        "phone": "0300 1234567",
        "email": "ahmed@example.com",
        "city": "Lahore",
        "business_type": "Retail / Grocery",
        "product_interest": "pos",
        "message": "Interested in a demo.",
    }
    base.update(over)
    return base


def test_valid_lead_creates_row_and_returns_201():
    api = APIClient()
    resp = api.post("/api/leads/", _payload(), format="json")
    assert resp.status_code == 201, resp.content
    assert Lead.objects.count() == 1
    lead = Lead.objects.get()
    assert lead.business_name == "Khan Super Store"
    assert lead.product_interest == "pos"
    assert lead.source == "website"


def test_missing_required_fields_returns_400():
    api = APIClient()
    resp = api.post("/api/leads/", _payload(business_name="", phone=""), format="json")
    assert resp.status_code == 400
    assert "business_name" in resp.json()
    assert Lead.objects.count() == 0


def test_invalid_phone_rejected():
    api = APIClient()
    resp = api.post("/api/leads/", _payload(phone="12"), format="json")
    assert resp.status_code == 400
    assert "phone" in resp.json()


def test_honeypot_drops_silently_without_creating_row():
    api = APIClient()
    resp = api.post("/api/leads/", _payload(company_website="http://spam.example"), format="json")
    # Bots get a friendly 201 but nothing is persisted.
    assert resp.status_code == 201
    assert Lead.objects.count() == 0


def test_email_sent_when_recipients_configured(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.LEADS_NOTIFY_EMAILS = ["sales@invoicesolution.pk"]
    api = APIClient()
    resp = api.post("/api/leads/", _payload(), format="json")
    assert resp.status_code == 201
    assert len(mail.outbox) == 1
    assert "Khan Super Store" in mail.outbox[0].subject
    assert "0300 1234567" in mail.outbox[0].body


def test_email_failure_does_not_lose_lead(settings, monkeypatch):
    settings.LEADS_NOTIFY_EMAILS = ["sales@invoicesolution.pk"]

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("apps.leads.views.send_mail", boom)
    api = APIClient()
    resp = api.post("/api/leads/", _payload(), format="json")
    # Request still succeeds; the lead is safely in the DB.
    assert resp.status_code == 201
    assert Lead.objects.count() == 1
