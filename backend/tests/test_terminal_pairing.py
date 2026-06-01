"""Terminal device-pairing flow.

The owner creates a Terminal in admin-web (which auto-issues a one-time pairing
code); the Electron terminal redeems the code via the PUBLIC /api/terminals/pair/
endpoint, binding the physical device (fingerprint) to that terminal slot and
receiving the branch identity it needs to ring sales + fiscalize.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Branch, Terminal


@pytest.fixture
def branch(db, tenant) -> Branch:
    return Branch.objects.create(
        tenant=tenant, name="Main Branch", code="MAIN",
        fbr_pos_id="194444", fbr_pos_code="3364862B",
    )


@pytest.fixture
def terminal(db, tenant, branch) -> Terminal:
    t = Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="unpaired-placeholder-abc",
    )
    t.issue_pairing_code()
    return t


def test_issue_pairing_code_is_unambiguous_and_expiring(terminal):
    assert terminal.pairing_code
    # Format K7P3-9QXM: 4-4 split, no ambiguous chars.
    raw = terminal.pairing_code.replace("-", "")
    assert len(raw) == 8
    assert not (set(raw) & set("01OIL"))
    assert terminal.pairing_code_expires_at > timezone.now()


def test_pair_success_binds_device_and_returns_branch_identity(terminal, branch):
    client = APIClient()
    resp = client.post("/api/terminals/pair/", {
        "pairing_code": terminal.pairing_code,
        "device_fingerprint": "REAL-MACHINE-FINGERPRINT-001",
        "os_version": "Windows 10",
        "app_version": "1.0.0",
    }, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["branch_id"] == str(branch.id)
    assert body["branch_code"] == "MAIN"
    assert body["branch_fbr_pos_id"] == "194444"
    assert body["terminal_id"] == str(terminal.id)
    assert body["terminal_index"] == terminal.terminal_index
    assert body["sdc_url"]  # defaults to localhost when unset

    terminal.refresh_from_db()
    assert terminal.device_fingerprint == "REAL-MACHINE-FINGERPRINT-001"
    assert terminal.paired_at is not None
    # Single-use: code is burned.
    assert terminal.pairing_code is None


def test_pair_is_public_no_auth_required(terminal):
    """The pairing endpoint must work with NO Authorization header."""
    client = APIClient()  # no credentials
    resp = client.post("/api/terminals/pair/", {
        "pairing_code": terminal.pairing_code,
        "device_fingerprint": "DEVICE-XYZ",
    }, format="json")
    assert resp.status_code == 200


def test_pair_code_is_single_use(terminal):
    client = APIClient()
    code = terminal.pairing_code
    first = client.post("/api/terminals/pair/", {
        "pairing_code": code, "device_fingerprint": "DEV-1",
    }, format="json")
    assert first.status_code == 200
    # Re-using the now-burned code fails.
    second = client.post("/api/terminals/pair/", {
        "pairing_code": code, "device_fingerprint": "DEV-2",
    }, format="json")
    assert second.status_code == 400


def test_pair_rejects_expired_code(terminal):
    terminal.pairing_code_expires_at = timezone.now() - timedelta(minutes=1)
    terminal.save(update_fields=["pairing_code_expires_at"])
    client = APIClient()
    resp = client.post("/api/terminals/pair/", {
        "pairing_code": terminal.pairing_code, "device_fingerprint": "DEV-1",
    }, format="json")
    assert resp.status_code == 400
    assert "expired" in str(resp.content).lower()


def test_pair_rejects_unknown_code(db):
    client = APIClient()
    resp = client.post("/api/terminals/pair/", {
        "pairing_code": "ZZZZ-ZZZZ", "device_fingerprint": "DEV-1",
    }, format="json")
    assert resp.status_code == 400


def test_pair_rejects_fingerprint_already_bound_elsewhere(terminal, tenant, branch):
    """One physical machine cannot pair as two terminals."""
    other = Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 2",
        device_fingerprint="ALREADY-USED-MACHINE",
    )
    other.issue_pairing_code()
    client = APIClient()
    resp = client.post("/api/terminals/pair/", {
        "pairing_code": terminal.pairing_code,
        "device_fingerprint": "ALREADY-USED-MACHINE",  # belongs to `other`
    }, format="json")
    assert resp.status_code == 400
    assert "already paired" in str(resp.content).lower()


def test_create_terminal_autoissues_code_and_placeholder_fingerprint(
    db, tenant, branch, owner_user,
):
    """POST /api/terminals/ from admin-web mints a code + placeholder device."""
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = RefreshToken.for_user(owner_user)
    token["tenant_id"] = str(tenant.id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    resp = client.post("/api/terminals/", {
        "branch": str(branch.id),
        "name": "Counter 3",
    }, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["pairing_code"]            # auto-issued
    assert body["is_paired"] is False
    assert body["device_fingerprint"].startswith("unpaired-")
