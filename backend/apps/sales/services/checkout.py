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

from django.core.exceptions import ValidationError
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
    # Warehouse to deduct stock from (Digital Invoicing only). None for POS /
    # legacy — stock is then branch-keyed exactly as before.
    warehouse=None,
    notes: str | None = None,
    local_invoice_number: str | None = None,
    invoice_type: str = "sale",
    reference_invoice: Invoice | None = None,
    reason: str | None = None,
    reason_notes: str | None = None,
    # Restaurant vertical (all optional; None for grocery/pharmacy/DI).
    order_type: str | None = None,
    table_id=None,
    covers: int | None = None,
    request=None,
    # Card proof fields (card_last4 / card_auth_code) are mandatory at the POS
    # terminal (the cashier has the slip in hand). Back-office MANUAL invoicing
    # keys invoices after the fact and may not have the slip — it passes False
    # so those fields become optional. Other methods are unaffected.
    require_card_details: bool = True,
) -> Invoice:
    """Create an invoice (sale, debit-note, or credit-note).

    invoice_type / reference_invoice were added in the V1 mid-cycle
    debit-note work — defaults preserve the original sale flow.
    Debit notes carry a reference to the original invoice so PRAL
    (and human auditors) can link them. The buyer block is copied
    from the reference when one is supplied and no `customer` arg
    overrides it.
    """
    # Idempotency: if we've already seen this client_uuid, return the prior row —
    # UNLESS it's a HELD open order (a restaurant order fired to the kitchen
    # before payment). A held order must be FINALIZED now (clear the hold, record
    # payment + stock + FBR), not returned as-is. We FINALIZE IT IN PLACE (reuse
    # the same row, keeping its local_invoice_number) rather than delete +
    # recreate — deleting would trip the DB-level DELETE grant on the append-only
    # fbr_submissions table that the Invoice FK points at.
    finalize_held: Invoice | None = None
    existing = Invoice.objects.filter(client_uuid=client_uuid).first()
    if existing is not None:
        if not existing.is_held:
            return existing  # already a finalized sale — true duplicate POST.
        finalize_held = existing
        finalize_held.items.all().delete()  # provisional snapshot, no payments/stock yet

    # Consistency: the terminal must belong to the invoice's branch. Otherwise
    # the invoice would be numbered under one branch but submitted to FBR under
    # that branch's token while the sale came from a terminal registered to a
    # different branch — mis-attributing it to the wrong POS registration.
    if terminal.branch_id != branch.id:
        raise ValidationError(
            f"Terminal {terminal.id} belongs to branch {terminal.branch_id}, "
            f"not the invoice branch {branch.id}. A terminal can only sell "
            f"under its own branch."
        )

    quote = quote_cart(cart_lines, cart_discount_pct=cart_discount_pct)
    paid_total = sum(Decimal(str(p["amount"])) for p in payments)

    # Buyer snapshot precedence:
    #   1. The customer arg (current sale flow).
    #   2. The reference invoice's buyer (debit/credit note flow — auditors
    #      need the buyer to match the original document exactly).
    if customer is not None:
        buyer_name = customer.name
        buyer_phone = customer.phone
        buyer_ntn_cnic = customer.ntn or customer.cnic
        buyer_province = customer.province
        buyer_reg = (
            "Registered" if customer.registration_type == "registered"
            else "Unregistered"
        )
    elif reference_invoice is not None:
        buyer_name = reference_invoice.buyer_name
        buyer_phone = reference_invoice.buyer_phone
        buyer_ntn_cnic = reference_invoice.buyer_ntn_cnic
        buyer_province = reference_invoice.buyer_province
        buyer_reg = reference_invoice.buyer_registration_type
    else:
        buyer_name = None
        buyer_phone = None
        buyer_ntn_cnic = None
        buyer_province = None
        buyer_reg = "Unregistered"

    invoice_fields = dict(
        tenant_id=tenant_id,
        branch=branch,
        terminal=terminal,
        warehouse=warehouse,
        cashier=cashier,
        cash_session=cash_session,
        customer=customer or (reference_invoice.customer if reference_invoice else None),
        # The invoice number is minted at CHARGE time. Finalizing a held order
        # ALWAYS mints a fresh server number (the held row only carried a
        # temporary order tag, never a real invoice number), so voided/abandoned
        # orders don't burn a number and completed invoices stay gapless. A
        # straight-through sale uses the number the terminal sent, else mints one.
        # (Previously a held order kept its tag, leaving gaps like "0032 → 0036".)
        local_invoice_number=(
            next_invoice_number(terminal=terminal) if finalize_held
            else (local_invoice_number or next_invoice_number(terminal=terminal))
        ),
        invoice_type=invoice_type,
        reference_invoice=reference_invoice,
        reason=reason,
        reason_notes=reason_notes,
        invoice_date=dt.date.today(),
        # Buyer snapshot — resolved above (customer arg, then reference, then None)
        buyer_name=buyer_name,
        buyer_phone=buyer_phone,
        buyer_ntn_cnic=buyer_ntn_cnic,
        buyer_province=buyer_province,
        buyer_registration_type=buyer_reg,
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
        # Restaurant: charging finalizes the order — clear the hold + mark served.
        order_type=order_type,
        table_id=table_id,
        covers=covers,
        order_status=("served" if order_type else None),
        is_held=False,
        kitchen_sent_at=(finalize_held.kitchen_sent_at if finalize_held else None),
    )

    if finalize_held is not None:
        # Finalize the held order in place: update its columns + keep the row.
        for attr, value in invoice_fields.items():
            setattr(finalize_held, attr, value)
        finalize_held.save()
        invoice = finalize_held
    else:
        invoice = Invoice.objects.create(**invoice_fields)

    # Pre-flight: any 3rd-Schedule product without a retail_price would
    # produce a PRAL rejection (errorCode 0122 — retail price > 0
    # required). Fail fast with a clear error so the operator fixes
    # the catalog instead of debugging a downstream FBR submission.
    third_schedule_missing_retail: list[str] = []
    for line_input in cart_lines:
        product = _resolve_product(tenant_id, line_input["product"])
        if (
            product.is_third_schedule
            and (product.retail_price is None or product.retail_price <= 0)
        ):
            third_schedule_missing_retail.append(
                f"{product.sku} ({product.name})",
            )
    if third_schedule_missing_retail:
        from rest_framework import serializers as drf_serializers
        raise drf_serializers.ValidationError({
            "cart_lines": (
                "These products are marked '3rd Schedule item' but have "
                "no retail price set, so PRAL will reject the invoice. "
                "Open the product in Catalog and set Retail price before "
                "ringing them up: "
                + ", ".join(third_schedule_missing_retail)
            ),
        })

    # Sale items + corresponding stock_movement (sale type, negative qty)
    for line_no, (line_input, line_quote) in enumerate(zip(cart_lines, quote.lines), start=1):
        product: Product = _resolve_product(tenant_id, line_input["product"])
        variant: ProductVariant | None = (
            _resolve_variant(line_input.get("variant")) if line_input.get("variant") else None
        )
        batch: ProductBatch | None = (
            ProductBatch.objects.get(pk=line_input["batch"]) if line_input.get("batch") else None
        )

        # 3rd-Schedule snapshot: PRAL rejects invoice lines for these
        # HS codes (sugar 1701.9910, biscuits, drinks, cigarettes, mobile
        # phones, etc.) unless fixedNotifiedValueOrRetailPrice > 0 AND
        # saleType="3rd Schedule Goods". We capture the marker + the
        # product's retail_price * qty onto SaleItem here so the FBR
        # builder doesn't need to re-fetch Product (which can be soft-
        # deleted or have its retail_price changed after the sale).
        #
        # FBR sale type resolution (3-tier, validated against PRAL's list so a
        # stale/free-typed string can never reach PRAL → errorCode 0204):
        #   1. an explicit cart-line override (manual / per-line select),
        #   2. else the product's configured sale_type,
        #   3. else the standard-rate default.
        # Tier 2 means existing POS terminals — which don't send sale_type —
        # automatically pick up product.sale_type without an exe rebuild.
        from apps.fbr.sale_types import DEFAULT_SALE_TYPE, is_valid_sale_type

        line_st = (line_input.get("sale_type") or "").strip()
        product_st = getattr(product, "sale_type", "") or ""
        if is_valid_sale_type(line_st):
            sale_type = line_st
        elif is_valid_sale_type(product_st):
            sale_type = product_st
        else:
            sale_type = DEFAULT_SALE_TYPE

        # 3rd-Schedule snapshot: tax is on the printed retail price, so freeze
        # retail_price * qty onto the SaleItem (the builder keys its retail math
        # off fixed_notified_value). Trigger on EITHER the mechanical flag or the
        # "3rd Schedule Goods" sale type, and force the saleType string to match
        # so PRAL's flag/string pairing is consistent (avoids error 0122).
        is_third = product.is_third_schedule or sale_type == "3rd Schedule Goods"
        if is_third and product.retail_price is not None:
            fixed_notified = product.retail_price * line_quote.quantity
            sale_type = "3rd Schedule Goods"
        else:
            fixed_notified = None

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
            fixed_notified_value=fixed_notified,
            sale_type=sale_type,
            # FBR SRO reference (reduced-rate / 8th-Schedule lines need it, or
            # PRAL rejects). Cart-line override → product's configured SRO.
            sro_schedule_no=(
                line_input.get("sro_schedule_no")
                or getattr(product, "sro_schedule_no", "") or None
            ),
            sro_item_serial_no=(
                line_input.get("sro_item_serial_no")
                or getattr(product, "sro_item_serial_no", "") or None
            ),
            # Restaurant snapshot (empty/None for other verticals). Modifier
            # price deltas are already folded into unit_price by the caller, so
            # totals + tax are correct; this list is for the receipt + KOT only.
            modifiers=line_input.get("modifiers") or [],
            course=line_input.get("course"),
            item_note=line_input.get("item_note"),
        )

        record_movement(
            tenant_id=tenant_id,
            product=product,
            variant=variant,
            batch=batch,
            branch=branch,
            warehouse=warehouse,
            movement_type="sale",
            quantity=Decimal("-1") * line_quote.quantity,
            unit_cost=product.cost_price,
            reference_type="invoice",
            reference_id=invoice.id,
            performed_by=cashier,
            reason=f"Sale {invoice.local_invoice_number}",
        )

    # Phase 5 — route every tender through the per-method adapter so the
    # method-specific fields (card_last4, wallet_transaction_id, etc.) are
    # validated + populated, and side effects (store_credit debit, ledger
    # entry, cheque pending status) fire correctly.
    from apps.payments.adapters import get_adapter
    for p in payments:
        adapter = get_adapter(p["payment_method"])
        adapter.record_payment(
            invoice=invoice,
            amount=Decimal(str(p["amount"])),
            data=p,
            user=cashier,
            require_details=require_card_details,
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
