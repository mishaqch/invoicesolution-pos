"""Phase 3 sync API tests."""

from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice
from apps.sync.models import SyncLog
from apps.tenants.models import Branch, Tenant, TenantMembership, Terminal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


User = get_user_model()


def _login(api: APIClient, email: str, password: str = "testpass1234"):
    resp = api.post(
        "/api/auth/login/",
        {"email": email, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['access']}")


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Defence", code="DHA",
        address="Main road", city="Karachi", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="sync-test-1",
    )


@pytest.fixture
def stocked_product(db, tenant, branch):
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(
        tenant=tenant, name="Apple", sku="APL-1", uom=uom,
        sale_price=Decimal("100"), cost_price=Decimal("60"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return p


@pytest.fixture
def second_tenant(db):
    t = Tenant.objects.create(
        business_name="Other Shop", ntn="OTH-1",
        business_type="sole_proprietor", province="PUNJAB",
    )
    return t


@pytest.fixture
def other_terminal(db, second_tenant):
    b = Branch.objects.create(
        tenant=second_tenant, name="Other branch", code="OTH",
        address="…", city="Lahore", province="PUNJAB",
    )
    return Terminal.objects.create(
        tenant=second_tenant, branch=b, name="Counter 1",
        device_fingerprint="other-tenant-fp",
    )


def _invoice_payload(*, terminal, branch, cashier, product, client_uuid, local_no="DHA-T1-2026-0009999"):
    return {
        "client_uuid": str(client_uuid),
        "terminal": str(terminal.id),
        "branch": str(branch.id),
        "cashier": str(cashier.id),
        "local_invoice_number": local_no,
        "cart_lines": [
            {
                "product": str(product.id),
                "quantity": "2",
                "unit_price": "100",
                "tax_rate": "18",
                "is_taxable": True,
            },
        ],
        "payments": [{"payment_method": "cash", "amount": "236"}],
    }


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_invoice_sync_creates_invoice_and_sync_log(
    owner_user, terminal, branch, stocked_product,
):
    api = APIClient()
    _login(api, "owner@example.com")

    payload = _invoice_payload(
        terminal=terminal, branch=branch, cashier=owner_user,
        product=stocked_product, client_uuid=uuid.uuid4(),
        local_no="DHA-T1-2026-0010001",
    )
    resp = api.post("/api/sync/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["sync_status"] == "processed"
    assert body["local_invoice_number"] == "DHA-T1-2026-0010001"
    assert Invoice.objects.filter(client_uuid=payload["client_uuid"]).count() == 1
    assert SyncLog.objects.filter(client_uuid=payload["client_uuid"]).count() == 1


@pytest.mark.django_db
def test_duplicate_client_uuid_returns_duplicate_status(
    owner_user, terminal, branch, stocked_product,
):
    api = APIClient()
    _login(api, "owner@example.com")

    cuid = uuid.uuid4()
    payload = _invoice_payload(
        terminal=terminal, branch=branch, cashier=owner_user,
        product=stocked_product, client_uuid=cuid,
        local_no="DHA-T1-2026-0010002",
    )
    resp1 = api.post("/api/sync/invoices/", payload, format="json")
    assert resp1.status_code == 201

    # Replay — same client_uuid.
    resp2 = api.post("/api/sync/invoices/", payload, format="json")
    assert resp2.status_code == 200, resp2.content
    body = resp2.json()
    assert body["sync_status"] == "duplicate"
    assert body["id"] == resp1.json()["id"]

    # Only one invoice was created.
    assert Invoice.objects.filter(client_uuid=cuid).count() == 1
    # Sync log is unique on client_uuid.
    assert SyncLog.objects.filter(client_uuid=cuid).count() == 1


# ---------------------------------------------------------------------------
# Cross-tenant
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cross_tenant_terminal_rejected(
    owner_user, terminal, branch, stocked_product, other_terminal,
):
    """Tenant A's user POSTs with tenant B's terminal_id → 404 (not visible)."""
    api = APIClient()
    _login(api, "owner@example.com")

    payload = _invoice_payload(
        terminal=other_terminal,  # belongs to tenant B
        branch=branch, cashier=owner_user, product=stocked_product,
        client_uuid=uuid.uuid4(),
    )
    resp = api.post("/api/sync/invoices/", payload, format="json")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# Failure → retry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_failed_sync_can_be_retried_after_fix(
    owner_user, terminal, branch, stocked_product,
):
    """A bad payload fails, gets fixed via retry endpoint."""
    api = APIClient()
    _login(api, "owner@example.com")

    payload = _invoice_payload(
        terminal=terminal, branch=branch, cashier=owner_user,
        product=stocked_product, client_uuid=uuid.uuid4(),
        local_no="DHA-T1-2026-0010003",
    )
    # Break the product reference — server will try to look it up and fail.
    payload["cart_lines"][0]["product"] = str(uuid.uuid4())

    resp = api.post("/api/sync/invoices/", payload, format="json")
    assert resp.status_code == 400, resp.content

    failed = SyncLog.objects.get(client_uuid=payload["client_uuid"])
    assert failed.status == "failed"

    # Fix the payload in place (retry uses the stored payload — so we mutate it).
    failed.payload["cart_lines"][0]["product"] = str(stocked_product.id)
    failed.save(update_fields=["payload", "updated_at"])

    retry_resp = api.post(f"/api/sync/log/{failed.id}/retry/", format="json")
    assert retry_resp.status_code == 200, retry_resp.content

    failed.refresh_from_db()
    assert failed.status == "processed"
    assert Invoice.objects.filter(client_uuid=payload["client_uuid"]).exists()


# ---------------------------------------------------------------------------
# Chaos test — 30% random failure, eventually consistent.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chaos_random_failures_eventually_consistent(
    owner_user, terminal, branch, stocked_product,
):
    """Simulate a flaky network: 30% of POSTs fail; the worker retries with
    the same client_uuid until success. End state: each unique client_uuid
    has exactly one invoice."""
    api = APIClient()
    _login(api, "owner@example.com")
    rng = random.Random(42)

    target_invoices = 20
    cuuids = [uuid.uuid4() for _ in range(target_invoices)]
    posted_ok: set = set()

    # Each client_uuid retries until it lands successfully.
    attempts = 0
    while len(posted_ok) < target_invoices and attempts < 200:
        attempts += 1
        for i, cuid in enumerate(cuuids):
            if cuid in posted_ok:
                continue
            payload = _invoice_payload(
                terminal=terminal, branch=branch, cashier=owner_user,
                product=stocked_product, client_uuid=cuid,
                local_no=f"DHA-T1-2026-002{i:04d}",
            )
            # Synthetic failure: 30% chance the network drops the request.
            if rng.random() < 0.3:
                continue
            resp = api.post("/api/sync/invoices/", payload, format="json")
            if resp.status_code in (200, 201):
                posted_ok.add(cuid)

    # Every client_uuid should now have exactly one invoice, no duplicates.
    assert len(posted_ok) == target_invoices
    for cuid in cuuids:
        assert Invoice.objects.filter(client_uuid=cuid).count() == 1


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sync_status_aggregates_pending_and_failed(
    owner_user, terminal, tenant,
):
    api = APIClient()
    _login(api, "owner@example.com")

    # Seed some sync_log rows directly.
    SyncLog.objects.create(
        tenant=tenant, terminal=terminal, client_uuid=uuid.uuid4(),
        entity_type="invoice", action="create", payload={}, status="received",
    )
    SyncLog.objects.create(
        tenant=tenant, terminal=terminal, client_uuid=uuid.uuid4(),
        entity_type="invoice", action="create", payload={}, status="failed",
    )
    SyncLog.objects.create(
        tenant=tenant, terminal=terminal, client_uuid=uuid.uuid4(),
        entity_type="invoice", action="create", payload={}, status="processed",
    )

    resp = api.get(f"/api/sync/status/?terminal_id={terminal.id}")
    assert resp.status_code == 200
    body = resp.json()
    row = body["results"][0]
    assert row["pending"] == 1
    assert row["failed"] == 1
