"""Phase 5 payments — adapters, split tender, store credit, cheque flows."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.customers.models import Customer
from apps.inventory.services.movements import record_movement
from apps.payments.adapters import PaymentValidationError, get_adapter
from apps.payments.services import mark_cheque_bounced, mark_cheque_cleared
from apps.sales.models import Invoice, Payment
from apps.sales.services import checkout
from apps.tenants.models import Branch, Tenant, TenantSettings, Terminal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="X", code="PMT",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="Counter 1",
        device_fingerprint="pmt-fp",
    )


@pytest.fixture
def stocked(db, tenant, branch):
    p = Product.objects.create(
        tenant=tenant, name="Item", sku="ITEM-1",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("1000"),
    )
    record_movement(
        tenant_id=tenant.id, product=p, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return p


@pytest.fixture
def customer(db, tenant):
    return Customer.objects.create(
        tenant=tenant, name="Test Customer",
        registration_type="registered",
        store_credit=Decimal("500"),
    )


def _checkout(tenant, branch, terminal, cashier, stocked, *, payments,
              customer=None, qty="1"):
    return checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=customer,
        cart_lines=[{
            "product": str(stocked.id),
            "quantity": qty,
            "unit_price": "1000",
            "tax_rate": "0",
            "is_taxable": False,
        }],
        payments=payments,
        client_uuid=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# TenantSettings auto-seed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_settings_seeded_on_tenant_create():
    t = Tenant.objects.create(
        business_name="New", ntn=f"NEW-{uuid.uuid4().hex[:6]}",
        business_type="sole_proprietor", province="PUNJAB",
    )
    s = TenantSettings.objects.get(tenant=t)
    assert s.enabled_payment_methods == ["cash"]


# ---------------------------------------------------------------------------
# Cash + card adapters
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_card_adapter_validates_last4_and_auth_code(
    tenant, branch, terminal, owner_user, stocked,
):
    adapter = get_adapter("card_credit")
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({"card_last4": "12", "card_auth_code": "123456"})
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({"card_last4": "1234", "card_auth_code": "12"})

    clean = adapter.validate_input({
        "card_last4": "1234", "card_auth_code": "654321", "card_rrn": "12345678",
    })
    assert clean == {
        "card_last4": "1234",
        "card_auth_code": "654321",
        "card_rrn": "12345678",
        "card_terminal_id": None,
    }


@pytest.mark.django_db
def test_card_rrn_optional(tenant, branch, terminal, owner_user, stocked):
    adapter = get_adapter("card_credit")
    clean = adapter.validate_input({
        "card_last4": "1234", "card_auth_code": "654321",
    })
    assert clean["card_rrn"] is None


@pytest.mark.django_db
def test_checkout_with_card_payment(
    tenant, branch, terminal, owner_user, stocked,
):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        payments=[{
            "payment_method": "card_credit",
            "amount": "1000",
            "card_last4": "4242",
            "card_auth_code": "888777",
            "card_rrn": "RRN-XYZ",
        }],
    )
    p = Payment.objects.get(invoice=inv)
    assert p.payment_method == "card_credit"
    assert p.card_last4 == "4242"
    assert p.card_auth_code == "888777"


# ---------------------------------------------------------------------------
# Wallet adapters
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_easypaisa_requires_transaction_id(
    tenant, branch, terminal, owner_user, stocked,
):
    adapter = get_adapter("easypaisa")
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({})


@pytest.mark.django_db
def test_checkout_with_easypaisa(tenant, branch, terminal, owner_user, stocked):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        payments=[{
            "payment_method": "easypaisa",
            "amount": "1000",
            "wallet_transaction_id": "EP-TX-99999",
            "wallet_phone": "03001234567",
        }],
    )
    p = Payment.objects.get(invoice=inv)
    assert p.wallet_provider == "easypaisa"
    assert p.wallet_transaction_id == "EP-TX-99999"


@pytest.mark.django_db
def test_checkout_with_raast(tenant, branch, terminal, owner_user, stocked):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        payments=[{
            "payment_method": "raast",
            "amount": "1000",
            "raast_transaction_id": "RAAST-9999",
            "raast_iban": "PK36SCBL0000001123456702",
        }],
    )
    p = Payment.objects.get(invoice=inv)
    assert p.payment_method == "raast"
    assert p.raast_transaction_id == "RAAST-9999"


# ---------------------------------------------------------------------------
# Bank transfer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bank_transfer_requires_bank_and_reference(
    tenant, branch, terminal, owner_user, stocked,
):
    adapter = get_adapter("bank_transfer")
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({"bank_name": "HBL"})  # missing ref
    with pytest.raises(PaymentValidationError):
        adapter.validate_input({"bank_reference": "X"})  # missing bank


# ---------------------------------------------------------------------------
# Store credit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_store_credit_requires_customer(
    tenant, branch, terminal, owner_user, stocked,
):
    """Without a customer on the sale, store_credit must refuse."""
    adapter = get_adapter("store_credit")
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        payments=[{"payment_method": "cash", "amount": "1000"}],
    )
    # Manually invoke the adapter to simulate retrying with store_credit.
    inv.customer = None
    with pytest.raises(PaymentValidationError):
        adapter.record_payment(invoice=inv, amount=Decimal("100"), data={})


@pytest.mark.django_db
def test_store_credit_debits_customer_balance(
    tenant, branch, terminal, owner_user, stocked, customer,
):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        customer=customer,
        payments=[
            {"payment_method": "store_credit", "amount": "300"},
            {"payment_method": "cash", "amount": "700"},
        ],
    )
    customer.refresh_from_db()
    assert customer.store_credit == Decimal("200.0000")  # 500 - 300
    payments = list(Payment.objects.filter(invoice=inv).order_by("created_at"))
    assert len(payments) == 2
    assert any(p.payment_method == "store_credit" for p in payments)


@pytest.mark.django_db
def test_store_credit_refuses_overdraw(
    tenant, branch, terminal, owner_user, stocked, customer,
):
    """Customer has Rs 500 store credit; trying to apply Rs 600 must fail."""
    with pytest.raises(PaymentValidationError):
        _checkout(
            tenant, branch, terminal, owner_user, stocked,
            customer=customer,
            payments=[{"payment_method": "store_credit", "amount": "600"}],
        )


# ---------------------------------------------------------------------------
# Cheque
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cheque_recorded_pending(tenant, branch, terminal, owner_user, stocked):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        payments=[{
            "payment_method": "cheque",
            "amount": "1000",
            "cheque_number": "CHQ-001",
            "bank_name": "HBL",
            "cheque_date": "2026-05-09",
        }],
    )
    p = Payment.objects.get(invoice=inv)
    assert p.cheque_status == "pending"


@pytest.mark.django_db
def test_mark_cheque_cleared(tenant, branch, terminal, owner_user, stocked):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        payments=[{
            "payment_method": "cheque", "amount": "1000",
            "cheque_number": "CHQ-A", "bank_name": "HBL",
            "cheque_date": "2026-05-09",
        }],
    )
    p = Payment.objects.get(invoice=inv)
    mark_cheque_cleared(p, user=owner_user)
    p.refresh_from_db()
    assert p.cheque_status == "cleared"


@pytest.mark.django_db
def test_mark_cheque_bounced_flags_customer(
    tenant, branch, terminal, owner_user, stocked, customer,
):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        customer=customer,
        payments=[{
            "payment_method": "cheque", "amount": "1000",
            "cheque_number": "CHQ-B", "bank_name": "MCB",
            "cheque_date": "2026-05-09",
        }],
    )
    p = Payment.objects.get(invoice=inv)
    mark_cheque_bounced(p, reason="insufficient funds", user=owner_user)
    p.refresh_from_db()
    customer.refresh_from_db()
    assert p.cheque_status == "bounced"
    assert "Cheque" in (customer.notes or "")
    assert "bounced" in (customer.notes or "")


# ---------------------------------------------------------------------------
# Split tender math
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_split_tender_three_methods(
    tenant, branch, terminal, owner_user, stocked, customer,
):
    inv = _checkout(
        tenant, branch, terminal, owner_user, stocked,
        customer=customer,
        payments=[
            {"payment_method": "cash", "amount": "400"},
            {"payment_method": "easypaisa", "amount": "300",
             "wallet_transaction_id": "EP-1"},
            {"payment_method": "store_credit", "amount": "300"},
        ],
    )
    inv.refresh_from_db()
    assert inv.paid_total == Decimal("1000.0000")
    payments = Payment.objects.filter(invoice=inv).count()
    assert payments == 3


# ---------------------------------------------------------------------------
# Cross-tenant TenantSettings isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_settings_per_tenant():
    a = Tenant.objects.create(
        business_name="A", ntn=f"A-{uuid.uuid4().hex[:6]}",
        business_type="sole_proprietor", province="PUNJAB",
    )
    b = Tenant.objects.create(
        business_name="B", ntn=f"B-{uuid.uuid4().hex[:6]}",
        business_type="sole_proprietor", province="SINDH",
    )
    a.settings.enabled_payment_methods = ["cash", "easypaisa"]
    a.settings.save()
    b.settings.enabled_payment_methods = ["cash"]
    b.settings.save()
    assert a.settings.enabled_payment_methods == ["cash", "easypaisa"]
    assert b.settings.enabled_payment_methods == ["cash"]
