"""Phase 2 sales tests — checkout, holds, sessions, cancel, audit, cross-tenant."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.signals import AuditLogImmutableError
from apps.catalog.models import Product, UnitOfMeasure
from apps.customers.models import Customer
from apps.inventory.models import StockLevel, StockMovement
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice, Payment, SaleItem
from apps.sales.services import cancellation, checkout, holds, sessions
from apps.tenants.models import Branch, CashSession, Tenant, TenantMembership, Terminal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        device_fingerprint="fp-test-1",
    )


@pytest.fixture
def uom(db):
    return UnitOfMeasure.objects.get(code="PCS")


@pytest.fixture
def product(db, tenant, uom):
    return Product.objects.create(
        tenant=tenant, name="Apple", sku="APL-1",
        uom=uom, sale_price=Decimal("100"),
        cost_price=Decimal("60"),
    )


@pytest.fixture
def stocked_product(db, tenant, branch, product):
    record_movement(
        tenant_id=tenant.id, product=product, branch=branch,
        movement_type="opening_balance", quantity=Decimal("100"),
    )
    return product


@pytest.fixture
def cashier(db, tenant):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.create_user(
        email="cashier-tx@example.com", password="testpass1234",
        full_name="Cashier Test",
    )
    TenantMembership.objects.create(tenant=tenant, user=u, role="cashier")
    return u


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_checkout_writes_invoice_items_payments_movements_audit(
    tenant, branch, terminal, cashier, stocked_product,
):
    initial_movements = StockMovement.objects.count()
    initial_audits = AuditLog.objects.count()

    invoice = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[
            {"product": str(stocked_product.id), "quantity": "2",
             "unit_price": "100", "tax_rate": "18", "is_taxable": True},
        ],
        payments=[{"payment_method": "cash", "amount": "236"}],
        client_uuid=str(uuid.uuid4()),
    )

    # Invoice persisted with totals
    invoice.refresh_from_db()
    assert invoice.subtotal == Decimal("200.0000")
    assert invoice.tax_total == Decimal("36.0000")
    assert invoice.grand_total == Decimal("236.0000")
    assert invoice.paid_total == Decimal("236.0000")
    assert invoice.change_given == Decimal("0.0000")
    assert invoice.status == "pending_sync"

    # Sale items
    items = list(SaleItem.objects.filter(invoice=invoice))
    assert len(items) == 1
    assert items[0].product_name == "Apple"
    assert items[0].line_total == Decimal("236.0000")

    # Payments
    assert Payment.objects.filter(invoice=invoice, payment_method="cash").count() == 1

    # Stock movement (sale, negative qty)
    assert StockMovement.objects.count() == initial_movements + 1
    sale_mvt = StockMovement.objects.filter(
        product=stocked_product, branch=branch, movement_type="sale",
    ).order_by("-created_at").first()
    assert sale_mvt is not None
    assert sale_mvt.quantity == Decimal("-2.0000")

    # Stock level reduced 100 → 98
    level = StockLevel.objects.get(product=stocked_product, branch=branch, variant=None)
    assert level.quantity == Decimal("98.0000")

    # Audit row appended
    assert AuditLog.objects.count() == initial_audits + 1
    audit = AuditLog.objects.filter(entity_id=invoice.id).first()
    assert audit.action == "create"


@pytest.mark.django_db
def test_checkout_idempotent_on_client_uuid(
    tenant, branch, terminal, cashier, stocked_product,
):
    cuuid = str(uuid.uuid4())
    invoice1 = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[
            {"product": str(stocked_product.id), "quantity": "1",
             "unit_price": "100", "tax_rate": "0", "is_taxable": False},
        ],
        payments=[{"payment_method": "cash", "amount": "100"}],
        client_uuid=cuuid,
    )
    invoice2 = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[
            {"product": str(stocked_product.id), "quantity": "1",
             "unit_price": "100", "tax_rate": "0", "is_taxable": False},
        ],
        payments=[{"payment_method": "cash", "amount": "100"}],
        client_uuid=cuuid,
    )
    assert invoice1.id == invoice2.id
    # Only one stock movement was written.
    assert StockMovement.objects.filter(
        reference_id=invoice1.id, movement_type="sale",
    ).count() == 1


@pytest.mark.django_db
def test_invoice_number_is_monotonic_per_terminal_per_year(
    tenant, branch, terminal, cashier, stocked_product,
):
    numbers = []
    for _ in range(3):
        inv = checkout.create_invoice(
            tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
            cash_session=None, customer=None,
            cart_lines=[
                {"product": str(stocked_product.id), "quantity": "1",
                 "unit_price": "10", "tax_rate": "0", "is_taxable": False},
            ],
            payments=[{"payment_method": "cash", "amount": "10"}],
            client_uuid=str(uuid.uuid4()),
        )
        numbers.append(inv.local_invoice_number)

    # All start with the right prefix and are strictly increasing.
    assert all(n.startswith(f"{branch.code}-T1-") for n in numbers)
    seqs = [int(n.split("-")[-1]) for n in numbers]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_hold_recall_round_trip(tenant, branch, terminal, cashier, stocked_product):
    invoice = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[
            {"product": str(stocked_product.id), "quantity": "1",
             "unit_price": "100", "tax_rate": "0", "is_taxable": False},
        ],
        payments=[{"payment_method": "cash", "amount": "100"}],
        client_uuid=str(uuid.uuid4()),
    )
    holds.hold(invoice, label="Ahmed", user=cashier)
    invoice.refresh_from_db()
    assert invoice.is_held is True
    assert invoice.held_label == "Ahmed"

    holds.recall(invoice, user=cashier)
    invoice.refresh_from_db()
    assert invoice.is_held is False
    assert invoice.held_label is None


# ---------------------------------------------------------------------------
# Cash sessions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_open_close_session_with_no_variance(
    tenant, branch, terminal, cashier, stocked_product,
):
    session = sessions.open_session(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        opening_amount=Decimal("5000"),
    )
    assert session.status == "open"

    # Ring up 2 × 100 cash sales tied to the session.
    for _ in range(2):
        checkout.create_invoice(
            tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
            cash_session=session, customer=None,
            cart_lines=[
                {"product": str(stocked_product.id), "quantity": "1",
                 "unit_price": "100", "tax_rate": "0", "is_taxable": False},
            ],
            payments=[{"payment_method": "cash", "amount": "100"}],
            client_uuid=str(uuid.uuid4()),
        )

    closed = sessions.close_session(session=session, declared_amount=Decimal("5200"))
    assert closed.status == "closed"
    assert closed.expected_amount == Decimal("5200.0000")
    assert closed.variance == Decimal("0.0000")


@pytest.mark.django_db
def test_session_close_records_variance(tenant, branch, terminal, cashier):
    session = sessions.open_session(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        opening_amount=Decimal("5000"),
    )
    closed = sessions.close_session(
        session=session, declared_amount=Decimal("4980"),
        variance_reason="cash drawer was short by 20",
    )
    assert closed.variance == Decimal("-20.0000")
    assert closed.variance_reason


@pytest.mark.django_db
def test_only_one_open_session_per_terminal(tenant, branch, terminal, cashier):
    sessions.open_session(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        opening_amount=Decimal("1000"),
    )
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        sessions.open_session(
            tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
            opening_amount=Decimal("1000"),
        )


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cancel_invoice_reverses_stock(
    tenant, branch, terminal, cashier, stocked_product,
):
    invoice = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[
            {"product": str(stocked_product.id), "quantity": "5",
             "unit_price": "100", "tax_rate": "0", "is_taxable": False},
        ],
        payments=[{"payment_method": "cash", "amount": "500"}],
        client_uuid=str(uuid.uuid4()),
    )
    pre = StockLevel.objects.get(product=stocked_product, branch=branch).quantity
    cancellation.cancel_invoice(invoice, reason="cashier mistake", user=cashier)
    invoice.refresh_from_db()
    assert invoice.status == "cancelled"
    post = StockLevel.objects.get(product=stocked_product, branch=branch).quantity
    assert post == pre + Decimal("5.0000")


# ---------------------------------------------------------------------------
# Audit immutability
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_audit_log_update_blocked_by_signal(tenant):
    entry = AuditLog.objects.create(
        tenant_id=tenant.id, entity_type="test", action="create",
    )
    entry.action = "tampered"
    with pytest.raises(AuditLogImmutableError):
        entry.save()


@pytest.mark.django_db
def test_audit_log_delete_blocked_by_signal(tenant):
    entry = AuditLog.objects.create(
        tenant_id=tenant.id, entity_type="test", action="create",
    )
    with pytest.raises(AuditLogImmutableError):
        entry.delete()


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cross_tenant_invoice_not_visible(
    tenant, branch, terminal, cashier, stocked_product,
):
    """An invoice created for tenant X is not in another tenant's queryset."""
    invoice = checkout.create_invoice(
        tenant_id=tenant.id, branch=branch, terminal=terminal, cashier=cashier,
        cash_session=None, customer=None,
        cart_lines=[
            {"product": str(stocked_product.id), "quantity": "1",
             "unit_price": "10", "tax_rate": "0", "is_taxable": False},
        ],
        payments=[{"payment_method": "cash", "amount": "10"}],
        client_uuid=str(uuid.uuid4()),
    )
    other = Tenant.objects.create(
        business_name="Other", ntn="OTH-1",
        business_type="sole_proprietor", province="PUNJAB",
    )
    qs = Invoice.objects.for_tenant(other.id)
    assert invoice not in qs
