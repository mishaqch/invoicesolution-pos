"""Phase 4 immutability + token encryption tests."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import connection

from apps.fbr.encryption import decrypt, encrypt
from apps.fbr.models import FbrSubmission, FbrToken
from apps.fbr.signals import (
    FbrInvoiceNumberImmutableError,
    FbrSubmissionImmutableError,
)
from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------


def test_encrypt_round_trip():
    plaintext = "PRAL-SANDBOX-TOKEN-1234"
    ct = encrypt(plaintext)
    assert ct != plaintext
    assert decrypt(ct) == plaintext


def test_encrypt_returns_different_ciphertexts_for_same_plaintext():
    """Fernet uses an IV per encryption — two encrypts should differ."""
    a = encrypt("same")
    b = encrypt("same")
    assert a != b
    assert decrypt(a) == decrypt(b) == "same"


def test_decrypt_rejects_tampered_ciphertext():
    ct = encrypt("hello")
    tampered = ct[:-2] + "XX"
    with pytest.raises(ValueError):
        decrypt(tampered)


@pytest.mark.django_db
def test_token_persisted_encrypted(tenant):
    obj = FbrToken.objects.create(
        tenant=tenant, environment="sandbox",
        token_encrypted="",  # set via property below
        api_endpoint="https://gw.fbr.gov.pk",
    )
    obj.set_token("PRAL-LIVE-FROM-IRIS")
    obj.save()

    # Pull the raw column from the DB and confirm it's not the plaintext.
    with connection.cursor() as cur:
        cur.execute("SELECT token_encrypted FROM fbr_tokens WHERE id = %s", [obj.id])
        raw = cur.fetchone()[0]
    assert raw != "PRAL-LIVE-FROM-IRIS"
    assert "PRAL-LIVE" not in raw

    # Round trip via the property still returns plaintext.
    obj.refresh_from_db()
    assert obj.token == "PRAL-LIVE-FROM-IRIS"


# ---------------------------------------------------------------------------
# fbr_submissions append-only (signal-level)
# ---------------------------------------------------------------------------


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="X", code="IM",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="im-fp",
    )


@pytest.mark.django_db
def test_fbr_submission_update_blocked_by_signal(tenant):
    sub = FbrSubmission.objects.create(
        tenant=tenant, environment="sandbox", endpoint="postinvoicedata",
        request_payload={}, attempt_number=1,
    )
    sub.error_message = "tampered"
    with pytest.raises(FbrSubmissionImmutableError):
        sub.save()


@pytest.mark.django_db
def test_fbr_submission_delete_blocked_by_signal(tenant):
    sub = FbrSubmission.objects.create(
        tenant=tenant, environment="sandbox", endpoint="postinvoicedata",
        request_payload={}, attempt_number=1,
    )
    with pytest.raises(FbrSubmissionImmutableError):
        sub.delete()


# ---------------------------------------------------------------------------
# invoices.fbr_invoice_number immutable post-validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fbr_invoice_number_signal_blocks_change(
    tenant, branch, terminal, owner_user,
):
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        local_invoice_number="IM-T1-2026-0000001",
        invoice_date=dt.date.today(),
        subtotal=Decimal("100"), grand_total=Decimal("118"),
        paid_total=Decimal("118"),
        client_uuid=uuid.uuid4(),
        fbr_invoice_number="ORIGINAL-FBR-NO",
    )
    inv.fbr_invoice_number = "TAMPERED-FBR-NO"
    with pytest.raises(FbrInvoiceNumberImmutableError):
        inv.save()


@pytest.mark.django_db
def test_fbr_invoice_number_db_trigger_blocks_raw_update(
    tenant, branch, terminal, owner_user,
):
    """Even raw SQL UPDATE is rejected by the trigger from migration 0002."""
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        local_invoice_number="IM-T1-2026-0000002",
        invoice_date=dt.date.today(),
        subtotal=Decimal("100"), grand_total=Decimal("118"),
        paid_total=Decimal("118"),
        client_uuid=uuid.uuid4(),
        fbr_invoice_number="ORIGINAL-FBR-NO-2",
    )
    if connection.vendor != "postgresql":
        pytest.skip("Trigger only enforced on Postgres")
    from django.db.utils import InternalError, ProgrammingError
    with pytest.raises((InternalError, ProgrammingError, Exception)) as exc_info:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE invoices SET fbr_invoice_number = %s WHERE id = %s",
                ["TAMPERED", str(inv.id)],
            )
    assert "immutable" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_fbr_invoice_number_can_transition_from_null_to_value(
    tenant, branch, terminal, owner_user,
):
    """Setting fbr_invoice_number for the first time is allowed."""
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=owner_user,
        local_invoice_number="IM-T1-2026-0000003",
        invoice_date=dt.date.today(),
        subtotal=Decimal("100"), grand_total=Decimal("118"),
        paid_total=Decimal("118"),
        client_uuid=uuid.uuid4(),
    )
    inv.fbr_invoice_number = "FIRST-FBR-NO"
    inv.save()  # should NOT raise
    inv.refresh_from_db()
    assert inv.fbr_invoice_number == "FIRST-FBR-NO"
