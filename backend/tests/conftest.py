"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.tenants.models import Tenant, TenantMembership


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(
        business_name="Khalil General Store",
        ntn="1234567",
        business_type="sole_proprietor",
        province="PUNJAB",
    )


@pytest.fixture
def owner_user(db, tenant) -> "User":  # type: ignore[name-defined]
    User = get_user_model()
    user = User.objects.create_user(
        email="owner@example.com",
        password="testpass1234",
        full_name="Demo Owner",
    )
    TenantMembership.objects.create(tenant=tenant, user=user, role="owner")
    return user


@pytest.fixture
def cashier_user(db, tenant):
    User = get_user_model()
    user = User.objects.create_user(
        email="cashier@example.com",
        password="testpass1234",
        full_name="Ahmed Khan",
    )
    user.set_pin("1234")
    user.save()
    TenantMembership.objects.create(tenant=tenant, user=user, role="cashier")
    return user
