"""Atomic create_invoice — write invoice + items + payments + stock + audit.

Single transaction. Returns the persisted Invoice.

Phase 2 ships this for cash-only sales. Other payment methods are wired in
Phase 5 but won't change this signature; the per-method validation lives
behind the payment_method enum check.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.catalog.models import Product, ProductBatch, ProductVariant
from apps.customers.models import Customer, CustomerLedger
from apps.inventory.services.movements import record_movement
from apps.sales.models import Invoice, Payment, SaleItem
from apps.sales.services.numbering import next_invoice_number
from apps.sales.services.pricing import quote_cart
from apps.tenants.models import Branch, CashSession, Terminal


@transaction.atomic
def create_invoice(
    *,
    tenant_id,
    branch: Branch,
    terminal: Terminal,
    cashier,
    cash_session: CashSession | None,
    customer: Customer | None,
    cart_lines: list[dict],
    cart_discount_pct: Decimal | str = 0,
    payments: list[dict],
    client_uuid: UUID | str,
    notes: str | None = None,
    local_invoice_number: str | None = None,
    request=None,
) -> Invoice:
    # Idempotency: if we've already seen this client_uuid, return the prior row.
    existing = Invoice.objects.filter(client_uuid=client_uuid).first()
    if existing is not None:
        return existing

    quote = quote_cart(cart_lines, cart_discount_pct=cart_discount_pct)
    paid_total = sum(Decimal(str(p["amount"])) for p in payments)

    invoice = Invoice.objects.create(
        tenant_id=tenant_id,
        branch=branch,
        terminal=terminal,
        cashier=cashier,
        cash_session=cash_session,
        customer=customer,
        local_invoice_number=local_invoice_number or next_invoice_number(terminal=terminal),
        invoice_type="sale",
        invoice_date=dt.date.today(),
        # Buyer snapshot
        buyer_name=customer.name if customer else None,
        buyer_phone=customer.phone if customer else None,
        buyer_ntn_cnic=(customer.ntn or customer.cnic) if customer else None,
        buyer_province=customer.province if customer else None,
        buyer_registration_type=(
            "Registered" if customer and customer.registration_type == "registered"
            else "Unregistered"
        ),
        # Money
        subtotal=quote.subtotal.amount,
        discount_total=quote.discount_total.amount,
        tax_total=quote.tax_total.amount,
        grand_total=quote.grand_total.amount,
        paid_total=paid_total,
        change_given=max(Decimal(0), paid_total - quote.grand_total.amount),
        # Idempotency
        client_uuid=client_uuid,
        notes=notes,
        status="pending_sync",
    )

    # Sale items + corresponding stock_movement (sale type, negative qty)
    for line_no, (line_input, line_quote) in enumerate(zip(cart_lines, quote.lines), start=1):
        product: Product = _resolve_product(tenant_id, line_input["product"])
        variant: ProductVariant | None = (
            _resolve_variant(line_input.get("variant")) if line_input.get("variant") else None
        )
        batch: ProductBatch | None = (
            ProductBatch.objects.get(pk=line_input["batch"]) if line_input.get("batch") else None
        )

        SaleItem.objects.create(
            invoice=invoice,
            line_number=line_no,
            product=product,
            variant=variant,
            batch=batch,
            product_name=product.name,
            product_sku=product.sku,
            hs_code=product.hs_code_id,
            uom_code=product.uom_id,
            quantity=line_quote.quantity,
            unit_price=line_quote.unit_price.amount,
            cost_price=product.cost_price,
            discount_pct=line_quote.discount_pct,
            discount_amount=line_quote.line_discount.amount,
            tax_rate=line_quote.tax_rate,
            tax_amount=line_quote.tax_amount.amount,
            line_total=line_quote.line_total.amount,
        )

        record_movement(
            tenant_id=tenant_id,
            product=product,
            variant=variant,
            batch=batch,
            branch=branch,
            movement_type="sale",
            quantity=Decimal("-1") * line_quote.quantity,
            unit_cost=product.cost_price,
            reference_type="invoice",
            reference_id=invoice.id,
            performed_by=cashier,
            reason=f"Sale {invoice.local_invoice_number}",
        )

    for p in payments:
        Payment.objects.create(
            tenant_id=tenant_id,
            invoice=invoice,
            customer=customer,
            payment_method=p["payment_method"],
            amount=Decimal(str(p["amount"])),
            received_by=cashier,
            status="completed",
        )

    # Customer ledger entry — only for registered customers (per Phase 2 plan).
    if customer is not None:
        _append_customer_ledger(
            tenant_id=tenant_id, customer=customer, invoice=invoice,
            grand_total=quote.grand_total.amount, paid_total=paid_total,
            user=cashier,
        )

    audit_log(
        tenant_id=tenant_id,
        user=cashier,
        entity_type="invoice",
        entity_id=invoice.id,
        action="create",
        after={
            "local_invoice_number": invoice.local_invoice_number,
            "grand_total": str(invoice.grand_total),
            "items": len(cart_lines),
        },
        request=request,
    )
    return invoice


def _resolve_product(tenant_id, product_id) -> Product:
    return Product.objects.for_tenant(tenant_id).get(pk=product_id)


def _resolve_variant(variant_id) -> ProductVariant:
    return ProductVariant.objects.get(pk=variant_id)


def _append_customer_ledger(
    *, tenant_id, customer: Customer, invoice: Invoice,
    grand_total: Decimal, paid_total: Decimal, user,
) -> None:
    """Lock the customer row, append a ledger entry, update running balance."""
    locked = Customer.objects.select_for_update().get(pk=customer.pk)
    delta = grand_total - paid_total  # > 0 means they now owe us
    new_balance = locked.current_balance + delta
    CustomerLedger.objects.create(
        tenant_id=tenant_id,
        customer=locked,
        transaction_type="sale",
        reference_type="invoice",
        reference_id=invoice.id,
        debit=delta if delta > 0 else Decimal(0),
        credit=-delta if delta < 0 else Decimal(0),
        running_balance=new_balance,
        notes=f"Sale {invoice.local_invoice_number}",
        created_by=user,
    )
    locked.current_balance = new_balance
    locked.save(update_fields=["current_balance", "updated_at"])
