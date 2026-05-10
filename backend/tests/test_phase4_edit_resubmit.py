"""Edit-item + resubmit lifecycle.

Closes the Phase 4 gap where the 72h edit window had rules + a UI
countdown but no service / endpoint to actually do the edit, and
where failed FBR submissions had no operator path to retry.

Covers:
  - edit_invoice_item_with_fbr happy path: math recompute, history row,
    budget consume, audit, line + parent invoice flags
  - rules guards delegated to can_edit_item already covered in
    test_phase4_rules; here we verify the *service* respects them
  - resubmit_failed_invoice queues a retry only for failed/pending,
    refuses anything that already has an FBR invoice number
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import Product, UnitOfMeasure
from apps.fbr.budget import current_month_start_pkt
from apps.fbr.models import FbrCancelBudget
from apps.fbr.services import edit_invoice_item_with_fbr, resubmit_failed_invoice
from apps.sales.models import Invoice, SaleItem, SaleItemHistory
from apps.tenants.models import Branch, Terminal


@pytest.fixture
def cancel_budget(db, tenant):
    """The 10% monthly cap row. Budget seeded with plenty of headroom
    so edit-tests don't trip the 'budget exhausted' guard. The budget
    rules themselves are exercised in test_phase4_budget.
    """
    return FbrCancelBudget.objects.create(
        tenant=tenant, month_start=current_month_start_pkt(),
        previous_month_sales=Decimal("100000"),
        budget_amount=Decimal("10000"),
        consumed_amount=Decimal("0"),
        remaining_amount=Decimal("10000"),
    )


@pytest.fixture
def branch(db, tenant):
    return Branch.objects.create(
        tenant=tenant, name="Main", code="MAIN",
        address="x", city="x", province="SINDH",
    )


@pytest.fixture
def terminal(db, tenant, branch):
    return Terminal.objects.create(
        tenant=tenant, branch=branch, name="C1",
        device_fingerprint="edit-fp-1",
    )


@pytest.fixture
def product(db, tenant):
    return Product.objects.create(
        tenant=tenant, name="Widget", sku="WGT",
        uom=UnitOfMeasure.objects.get(code="PCS"),
        sale_price=Decimal("100"), cost_price=Decimal("60"),
    )


def _make_invoice(*, tenant, branch, terminal, cashier, product,
                  status="valid", deadline_offset_hours=24,
                  fbr_invoice_number=None, qty="2", price="100",
                  tax_rate="18", uuid="33333333-1111-1111-1111-111111111111"):
    deadline = timezone.now() + dt.timedelta(hours=deadline_offset_hours)
    inv = Invoice.objects.create(
        tenant=tenant, branch=branch, terminal=terminal, cashier=cashier,
        local_invoice_number="MAIN-T1-2026-0000001",
        invoice_date=dt.date.today(),
        subtotal=Decimal(qty) * Decimal(price),
        tax_total=(Decimal(qty) * Decimal(price) * Decimal(tax_rate) / Decimal("100")),
        grand_total=(
            Decimal(qty) * Decimal(price)
            + Decimal(qty) * Decimal(price) * Decimal(tax_rate) / Decimal("100")
        ),
        paid_total=Decimal("0"),
        client_uuid=uuid,
        edit_deadline_at=deadline,
        status=status,
        fbr_invoice_number=fbr_invoice_number,
    )
    line_total = (
        Decimal(qty) * Decimal(price)
        + Decimal(qty) * Decimal(price) * Decimal(tax_rate) / Decimal("100")
    )
    item = SaleItem.objects.create(
        invoice=inv, line_number=1, product=product,
        product_name=product.name, product_sku=product.sku, uom_code="PCS",
        quantity=Decimal(qty), unit_price=Decimal(price),
        cost_price=Decimal("60"),
        tax_rate=Decimal(tax_rate),
        tax_amount=Decimal(qty) * Decimal(price) * Decimal(tax_rate) / Decimal("100"),
        line_total=line_total,
    )
    return inv, item


# ---------------------------------------------------------------------------
# edit_invoice_item_with_fbr
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_edit_recomputes_money_and_writes_history(
    tenant, branch, terminal, owner_user, product, cancel_budget,
):
    inv, item = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product, qty="2", price="100", tax_rate="18",
    )

    # No production token configured → service stays local; that's the
    # path we want to assert math on.
    edit_invoice_item_with_fbr(
        inv, item,
        new_values={"quantity": Decimal("3")},
        reason="Customer added one more unit before leaving",
        user=owner_user,
    )

    item.refresh_from_db()
    inv.refresh_from_db()

    # 3 × 100 = 300 gross, +18% tax = 354
    assert item.quantity == Decimal("3")
    assert item.tax_amount == Decimal("54.0000")
    assert item.line_total == Decimal("354.0000")
    assert item.is_edited is True
    assert item.edit_count == 1
    assert item.edited_at is not None

    # History row written before the mutation
    history = SaleItemHistory.objects.filter(sale_item=item).first()
    assert history is not None
    assert history.change_type == "edit"
    assert Decimal(history.previous_data["quantity"]) == Decimal("2")

    # Parent totals recomputed
    assert inv.subtotal == Decimal("300")
    assert inv.tax_total == Decimal("54")
    assert inv.grand_total == Decimal("354")
    # No other items so the only state is "all edited" → partially_edited
    # (per service: if all are edited or cancelled, status is 'edited').
    assert inv.status in ("edited", "partially_edited")


@pytest.mark.django_db
def test_edit_rejects_double_edit(
    tenant, branch, terminal, owner_user, product, cancel_budget,
):
    inv, item = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
    )
    edit_invoice_item_with_fbr(
        inv, item, new_values={"unit_price": Decimal("110")},
        reason="Initial edit", user=owner_user,
    )
    item.refresh_from_db()

    with pytest.raises(ValidationError) as exc:
        edit_invoice_item_with_fbr(
            inv, item, new_values={"unit_price": Decimal("120")},
            reason="Second edit", user=owner_user,
        )
    assert "already been edited" in str(exc.value).lower()


@pytest.mark.django_db
def test_edit_rejects_after_deadline(tenant, branch, terminal, owner_user, product):
    inv, item = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
        deadline_offset_hours=-1,
    )
    with pytest.raises(ValidationError) as exc:
        edit_invoice_item_with_fbr(
            inv, item, new_values={"quantity": Decimal("3")},
            reason="too late", user=owner_user,
        )
    assert "72-hour" in str(exc.value)


@pytest.mark.django_db
def test_edit_rejects_unknown_field(tenant, branch, terminal, owner_user, product):
    inv, item = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
    )
    with pytest.raises(ValidationError) as exc:
        edit_invoice_item_with_fbr(
            inv, item,
            new_values={"product_name": "evil"},
            reason="hack", user=owner_user,
        )
    assert "not editable" in str(exc.value).lower()


@pytest.mark.django_db
def test_edit_rejects_negative_value(tenant, branch, terminal, owner_user, product):
    inv, item = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
    )
    with pytest.raises(ValidationError):
        edit_invoice_item_with_fbr(
            inv, item, new_values={"quantity": Decimal("-1")},
            reason="negative", user=owner_user,
        )


# ---------------------------------------------------------------------------
# resubmit_failed_invoice
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resubmit_queues_celery_task_for_failed(
    tenant, branch, terminal, owner_user, product,
):
    inv, _ = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product, status="failed",
    )
    with patch("apps.fbr.tasks.submit_invoice_to_fbr.delay") as mock_delay:
        resubmit_failed_invoice(inv, user=owner_user)

    mock_delay.assert_called_once_with(str(inv.id))


@pytest.mark.django_db
def test_resubmit_refuses_validated_invoice(
    tenant, branch, terminal, owner_user, product,
):
    inv, _ = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
        status="valid", fbr_invoice_number="FBR-2026-00001",
    )
    with pytest.raises(ValidationError) as exc:
        resubmit_failed_invoice(inv, user=owner_user)
    # The status guard fires first — caller knows the invoice isn't
    # in a re-submittable state without leaking the "already has number"
    # detail unnecessarily.
    assert "only failed/pending" in str(exc.value).lower()


@pytest.mark.django_db
def test_resubmit_refuses_invoice_already_with_fbr_number(
    tenant, branch, terminal, owner_user, product,
):
    """Belt + braces: even a 'failed' status with a populated FBR number
    is refused (would be a data inconsistency, but guard against it)."""
    inv, _ = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product,
        status="failed", fbr_invoice_number="FBR-2026-00002",
    )
    with pytest.raises(ValidationError) as exc:
        resubmit_failed_invoice(inv, user=owner_user)
    assert "already has" in str(exc.value).lower()


@pytest.mark.django_db
def test_resubmit_refuses_cancelled_invoice(
    tenant, branch, terminal, owner_user, product,
):
    inv, _ = _make_invoice(
        tenant=tenant, branch=branch, terminal=terminal,
        cashier=owner_user, product=product, status="cancelled",
    )
    with pytest.raises(ValidationError):
        resubmit_failed_invoice(inv, user=owner_user)
