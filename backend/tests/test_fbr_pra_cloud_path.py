"""PRA Cloud IMS submission path (fbr_connection_type='pra_cloud').

When a tenant is configured for pra_cloud AND its branch has an FBR POS ID AND a
PRA cloud token exists, the invoice is posted from OUR server to PRAL's cloud
(ims.pral.com.pk/.../Live/PostData) with a Bearer token — reusing the same
POS-Component payload/response as the local SDC. We mock the HTTP call and
assert: the correct cloud URL + Bearer header + per-branch POSID are sent, the
returned fiscal number persists, and the invoice goes valid. A TLS/network
failure (e.g. server not yet IP-whitelisted) is transient → invoice not
hard-failed on the first attempt.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
import requests

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.models import FbrToken
from apps.fbr.tasks import submit_invoice_to_fbr
from apps.inventory.services.movements import record_movement
from apps.sales.services import checkout
from apps.tenants.models import Branch, Terminal


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="AYUB SAB", code="BM1", address="x",
        city="Lahore", province="PUNJAB", fbr_pos_id="196819",
    )


@pytest.fixture
def cloud_setup(db, tenant, branch, owner_user):
    tenant.fbr_connection_type = "pra_cloud"
    tenant.save(update_fields=["fbr_connection_type"])
    tok = FbrToken(tenant=tenant, environment="sandbox", is_active=True,
                   api_endpoint="https://ims.pral.com.pk")
    tok.token = "test-bearer-token-123"
    tok.save()

    term = Terminal.objects.create(tenant=tenant, branch=branch, name="C1",
                                   device_fingerprint="prac-" + uuid.uuid4().hex[:8])
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="Biryani", sku="BM-1", uom=uom,
                               sale_price=Decimal("388"), cost_price=Decimal("100"))
    record_movement(tenant_id=tenant.id, product=p, branch=branch,
                    movement_type="opening_balance", quantity=Decimal("50"))
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=term, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(p.id), "quantity": "1", "unit_price": "388",
                     "tax_rate": "16", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "450.08"}],
        client_uuid=str(uuid.uuid4()),
    )
    return inv


def _mock_cloud_post(captured):
    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        captured["url"] = url
        captured["body"] = json
        captured["headers"] = headers or {}

        class _R:
            status_code = 200
            text = "ok"

            def json(self_inner):
                return {
                    "InvoiceNumber": "9000052011142444901",
                    "Code": "100",
                    "Response": "Fiscal Invoice Number generated successfully.",
                    "Errors": None,
                }
        return _R()
    return patch("apps.fbr.sdc_client.requests.post", side_effect=fake_post)


@pytest.mark.django_db
def test_pra_cloud_path_posts_with_bearer_and_posid(cloud_setup, tenant):
    inv = cloud_setup
    captured = {}
    with _mock_cloud_post(captured):
        result = submit_invoice_to_fbr(str(inv.id))

    assert result.get("via") == "pra_cloud", result
    assert result.get("ok") is True
    # PRA now posts to the unified gateway single-invoice path (the old
    # ims.pral.com.pk host is IP-blocked; ims/production Live/PostData is a
    # retired bulk endpoint). Overridable via FBR_PRA_CLOUD_URL.
    assert captured["url"] == "https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData"
    # Bearer token header
    assert captured["headers"].get("Authorization") == "Bearer test-bearer-token-123"
    # Per-branch POS ID in the PRA payload
    assert captured["body"]["POSID"] == 196819
    # Fiscal number persisted, invoice valid
    inv.refresh_from_db()
    assert inv.status == "valid"
    assert inv.fbr_invoice_number == "9000052011142444901"


@pytest.mark.django_db
def test_pra_cloud_tls_failure_is_transient(cloud_setup, tenant):
    """A TLS/SSL error (server not yet IP-whitelisted) must be TRANSIENT — the
    task schedules a Celery retry (raises Retry) rather than hard-failing the
    invoice. Called directly (not via a worker), self.retry() raises Retry."""
    from celery.exceptions import Retry
    from apps.fbr.sdc_client import SdcTransientError

    inv = cloud_setup

    def boom(*a, **k):
        raise requests.exceptions.SSLError("EOF occurred in violation of protocol")

    # self.retry(exc=...) re-raises to signal a retry: called directly (not via a
    # worker) it surfaces as the original transient error or a Retry — either way
    # it is NOT a hard failure/reject.
    with patch("apps.fbr.sdc_client.requests.post", side_effect=boom):
        with pytest.raises((Retry, SdcTransientError)):
            submit_invoice_to_fbr(str(inv.id))

    inv.refresh_from_db()
    # Not hard-failed — it was submitted and will be retried.
    assert inv.status == "submitted"


@pytest.mark.django_db
def test_pra_cloud_deferred_without_token(cloud_setup, tenant):
    """pra_cloud tenant with the token removed → defer cleanly (no crash)."""
    inv = cloud_setup
    FbrToken.objects.filter(tenant=tenant).update(is_active=False)
    with patch("apps.fbr.sdc_client.requests.post") as post:
        result = submit_invoice_to_fbr(str(inv.id))
    post.assert_not_called()
    assert result.get("deferred") == "no_pra_cloud_token", result


# --- FBR cloud (imsp Live/PostData) ------------------------------------------
# FBR POS (POS-DI / IsCloud) fiscalizes via gw.fbr.gov.pk/imsp/v1/api/Live/PostData
# with a per-branch Bearer token — same Live/PostData contract as PRA, on FBR's
# gateway. Verified live for PEER TRADERS (fiscal no. 194444FGQK...).

@pytest.mark.django_db
def test_fbr_cloud_path_used_for_di_api_pos_branch(db, tenant, owner_user):
    from apps.tenants.models import Branch, Terminal
    from apps.catalog.models import Product, UnitOfMeasure
    from apps.inventory.services.movements import record_movement
    from apps.sales.services import checkout
    from apps.fbr.models import BranchFbrToken

    tenant.fbr_connection_type = "di_api"
    tenant.save(update_fields=["fbr_connection_type"])
    br = Branch.objects.create(tenant=tenant, name="PEER", code="PT1", address="x",
                               city="Lahore", province="PUNJAB", fbr_pos_id="194444")
    term = Terminal.objects.create(tenant=tenant, branch=br, name="C1",
                                   device_fingerprint="fbrc-" + uuid.uuid4().hex[:8])
    bt = BranchFbrToken(branch=br, tenant_id=tenant.id, environment="production",
                        is_active=True, api_endpoint="https://gw.fbr.gov.pk")
    bt.token = "fbr-pos-bearer-xyz"
    bt.save()
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="Item", sku="FBR-1", uom=uom,
                               sale_price=Decimal("100"), cost_price=Decimal("50"))
    record_movement(tenant_id=tenant.id, product=p, branch=br,
                    movement_type="opening_balance", quantity=Decimal("10"))
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=br, terminal=term, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(p.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "18", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "118"}],
        client_uuid=str(uuid.uuid4()),
    )
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["posid"] = (json or {}).get("POSID")

        class _R:
            status_code = 200
            text = "ok"

            def json(self_inner):
                return {"InvoiceNumber": "194444FGQK99999999", "Code": "100",
                        "Response": "Invoice received successfully"}
        return _R()

    with patch("apps.fbr.sdc_client.requests.post", side_effect=fake_post):
        result = submit_invoice_to_fbr(str(inv.id))

    assert result.get("via") == "fbr_cloud", result
    assert result.get("ok") is True
    assert captured["url"] == "https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData"
    assert captured["headers"].get("Authorization") == "Bearer fbr-pos-bearer-xyz"
    assert captured["posid"] == 194444
    inv.refresh_from_db()
    assert inv.status == "valid"
    assert inv.fbr_invoice_number == "194444FGQK99999999"


# --- Gap fix: PRA POS prefers a per-branch token (multi-branch support) ------

@pytest.mark.django_db
def test_pra_cloud_prefers_branch_token(db, tenant, owner_user):
    """A pra_cloud tenant with a per-branch BranchFbrToken must submit under THAT
    token (each PRA POS branch = its own registration), not only the tenant
    token. Previously the branch token set on the Branches page was ignored."""
    from apps.tenants.models import Branch, Terminal
    from apps.catalog.models import Product, UnitOfMeasure
    from apps.inventory.services.movements import record_movement
    from apps.sales.services import checkout
    from apps.fbr.models import BranchFbrToken, FbrToken

    tenant.fbr_connection_type = "pra_cloud"
    tenant.save(update_fields=["fbr_connection_type"])
    # A tenant token exists too — the branch token must WIN.
    tt = FbrToken(tenant=tenant, environment="production", is_active=True,
                  api_endpoint="https://ims.pral.com.pk")
    tt.token = "tenant-level-token"
    tt.save()
    br = Branch.objects.create(tenant=tenant, name="AYUB", code="BM1", address="x",
                               city="Lahore", province="PUNJAB", fbr_pos_id="196819")
    bt = BranchFbrToken(branch=br, tenant_id=tenant.id, environment="production",
                        is_active=True, api_endpoint="https://ims.pral.com.pk")
    bt.token = "branch-pos-token"
    bt.save()
    term = Terminal.objects.create(tenant=tenant, branch=br, name="C1",
                                   device_fingerprint="prab-" + uuid.uuid4().hex[:8])
    uom = UnitOfMeasure.objects.get(code="PCS")
    p = Product.objects.create(tenant=tenant, name="Biryani", sku="BM-2", uom=uom,
                               sale_price=Decimal("100"), cost_price=Decimal("50"))
    record_movement(tenant_id=tenant.id, product=p, branch=br,
                    movement_type="opening_balance", quantity=Decimal("10"))
    inv = checkout.create_invoice(
        tenant_id=tenant.id, branch=br, terminal=term, cashier=owner_user,
        cash_session=None, customer=None,
        cart_lines=[{"product": str(p.id), "quantity": "1", "unit_price": "100",
                     "tax_rate": "16", "is_taxable": True}],
        payments=[{"payment_method": "cash", "amount": "116"}],
        client_uuid=str(uuid.uuid4()),
    )
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        captured["headers"] = headers or {}

        class _R:
            status_code = 200
            text = "ok"

            def json(self_inner):
                return {"InvoiceNumber": "196819PRA00000001", "Code": "100", "Response": "ok"}
        return _R()

    with patch("apps.fbr.sdc_client.requests.post", side_effect=fake_post):
        result = submit_invoice_to_fbr(str(inv.id))

    assert result.get("via") == "pra_cloud", result
    # Submitted under the BRANCH token, not the tenant token.
    assert captured["headers"].get("Authorization") == "Bearer branch-pos-token"
