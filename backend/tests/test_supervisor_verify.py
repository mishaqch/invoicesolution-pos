"""Supervisor-PIN verification for till actions (void/edit/discount).

Security contract:
  - Only an ACTIVE owner/manager of the SAME tenant can authorize.
  - A cashier PIN is rejected (the whole point — cashiers can't self-approve).
  - A manager from a DIFFERENT tenant is rejected.
  - Wrong PIN rejected. No token is ever issued. The check is audit-logged.
  - Endpoint requires the requesting cashier to be authenticated.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant, TenantMembership

User = get_user_model()


def _user(email, pin, tenant, role):
    u = User.objects.create_user(email=email, password="x12345678", full_name=email.split("@")[0])
    u.set_pin(pin)
    u.save()
    TenantMembership.objects.create(tenant=tenant, user=u, role=role)
    return u


def _client_as(user, tenant):
    c = APIClient()
    tok = RefreshToken.for_user(user)
    tok["tenant_id"] = str(tenant.id)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok.access_token}")
    return c


@pytest.fixture
def shop(db):
    return Tenant.objects.create(
        business_name="Shop A", ntn="111", business_type="sole_proprietor", province="PUNJAB")


@pytest.fixture
def cashier(db, shop):
    return _user("cashier@a.com", "111111", shop, "cashier")


@pytest.fixture
def manager(db, shop):
    return _user("manager@a.com", "222222", shop, "manager")


def _verify(client, email, pin, action="void_line"):
    return client.post("/api/auth/supervisor-verify/",
                       {"email": email, "pin": pin, "action": action}, format="json")


@pytest.mark.django_db
def test_manager_pin_authorizes(shop, cashier, manager):
    client = _client_as(cashier, shop)
    r = _verify(client, "manager@a.com", "222222")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["valid"] is True
    assert body["role"] == "manager"
    # No token leaked.
    assert "access" not in body and "refresh" not in body


@pytest.mark.django_db
def test_cashier_pin_rejected(shop, cashier):
    client = _client_as(cashier, shop)
    r = _verify(client, "cashier@a.com", "111111")
    assert r.status_code == 400  # a cashier cannot self-authorize


@pytest.mark.django_db
def test_wrong_pin_rejected(shop, cashier, manager):
    client = _client_as(cashier, shop)
    r = _verify(client, "manager@a.com", "999999")
    assert r.status_code == 400


@pytest.mark.django_db
def test_manager_from_other_tenant_rejected(db, shop, cashier):
    other = Tenant.objects.create(
        business_name="Shop B", ntn="222", business_type="sole_proprietor", province="SINDH")
    _user("mgr@b.com", "333333", other, "manager")  # manager of a DIFFERENT tenant
    client = _client_as(cashier, shop)
    r = _verify(client, "mgr@b.com", "333333")
    assert r.status_code == 400  # not a supervisor of THIS tenant


@pytest.mark.django_db
def test_requires_authentication(shop, manager):
    r = APIClient().post("/api/auth/supervisor-verify/",
                         {"email": "manager@a.com", "pin": "222222"}, format="json")
    assert r.status_code in (401, 403)


@pytest.mark.django_db
def test_authorization_is_audit_logged(shop, cashier, manager):
    from apps.audit.models import AuditLog
    before = AuditLog.objects.count()
    client = _client_as(cashier, shop)
    _verify(client, "manager@a.com", "222222", action="void_line")
    assert AuditLog.objects.count() == before + 1
    row = AuditLog.objects.filter(entity_type="approval").order_by("-created_at").first()
    assert row is not None
    assert "supervisor_authorized" in row.action
