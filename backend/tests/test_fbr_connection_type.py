"""fbr_connection_type drives mode-aware FBR UI.

The flag is orthogonal to business_mode: it records HOW a tenant reaches FBR
(direct DI-API with a token + scenarios, vs the IMS/SDC Fiscalization service
which uses a POS ID and no token). /api/me/modules/ surfaces it so admin-web can
hide the irrelevant FBR controls.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant


def _auth(client, user, tenant):
    token = RefreshToken.for_user(user)
    token["tenant_id"] = str(tenant.id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")


def test_default_connection_type_is_di_api(tenant):
    assert tenant.fbr_connection_type == "di_api"


def test_me_modules_exposes_connection_type(db, tenant, owner_user):
    client = APIClient()
    _auth(client, owner_user, tenant)
    resp = client.get("/api/me/modules/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["fbr_connection_type"] == "di_api"
    assert body["business_mode"] == tenant.business_mode
    # Still returns the module catalog + enabled set (unchanged contract).
    assert "catalog" in body and "enabled" in body


def test_me_modules_reports_ims_sdc(db, owner_user):
    # A tenant explicitly on the IMS/SDC path.
    t = Tenant.objects.create(
        business_name="Peer Traders", ntn="7886736-0",
        business_type="sole_proprietor", province="PUNJAB",
        business_mode="both", fbr_connection_type="ims_sdc",
    )
    from apps.tenants.models import TenantMembership
    TenantMembership.objects.create(tenant=t, user=owner_user, role="owner")

    client = APIClient()
    _auth(client, owner_user, t)
    resp = client.get("/api/me/modules/")
    assert resp.status_code == 200, resp.content
    assert resp.json()["fbr_connection_type"] == "ims_sdc"
