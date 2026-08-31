"""Restaurant order services — kitchen firing + floor/table aggregation.

Orders ARE held sales.Invoices (no separate model). These helpers operate on
that invoice's restaurant fields. KOT printing happens on the terminal; the
server only records that an order was fired (status + timestamp) and exposes
the kitchen queue + floor map.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.sales.models import Invoice, SaleItem
from apps.sales.services.pricing import quote_cart


@transaction.atomic
def upsert_open_order(*, tenant_id, branch, terminal, cashier, payload, request=None) -> Invoice:
    """Create or update an OPEN (held, unpaid) restaurant order on the server.

    Called from the terminal when the cashier fires the kitchen, so the live
    Floor + KDS see the order during service (not just after payment). The order
    is a held Invoice with restaurant fields + a priced item snapshot — NO
    payments, NO stock movement, NO FBR. Those happen later at Charge (the
    existing checkout flow, keyed on the same client_uuid → idempotent).

    Idempotent on client_uuid: re-firing replaces the item snapshot + bumps
    kitchen_sent_at, and marks every line sent_to_kitchen.
    """
    from apps.catalog.models import Product
    from apps.customers.models import Customer
    from apps.tenants.models import Branch  # noqa: F401 (type clarity)

    client_uuid = payload["client_uuid"]
    cart_lines = payload.get("cart_lines", [])
    quote = quote_cart(cart_lines, cart_discount_pct=payload.get("cart_discount_pct", 0))
    # fire=True  → the cashier hit "Send to kitchen": the order goes on the KDS
    #              (status sent_to_kitchen, kitchen_sent_at stamped, lines fired).
    # fire=False → the cashier hit "Save order": the order is PARKED in Open
    #              orders WITHOUT alerting the kitchen (status open, no KOT).
    # Default True preserves the original single-button behaviour for callers
    # (e.g. the auto-fire on Charge) that don't pass the flag.
    fire = payload.get("fire", True)

    customer = None
    if payload.get("customer"):
        customer = Customer.objects.for_tenant(tenant_id).filter(pk=payload["customer"]).first()

    table_id = payload.get("table")
    invoice = Invoice.objects.filter(tenant_id=tenant_id, client_uuid=client_uuid).first()
    is_new = invoice is None
    if is_new:
        from apps.sales.services.numbering import next_invoice_number
        invoice = Invoice(
            tenant_id=tenant_id, branch=branch, terminal=terminal, cashier=cashier,
            client_uuid=client_uuid, invoice_type="sale",
            local_invoice_number=payload.get("local_invoice_number") or next_invoice_number(terminal=terminal),
            invoice_date=dt.date.today(), status="pending_sync",
        )

    # Restaurant fields + buyer snapshot.
    invoice.is_held = True
    invoice.order_type = payload.get("order_type")
    invoice.table_id = table_id
    invoice.covers = payload.get("covers")
    if fire:
        # Firing: advance to sent_to_kitchen and stamp the time.
        invoice.order_status = "sent_to_kitchen"
        invoice.kitchen_sent_at = timezone.now()
    else:
        # Saving without firing: keep it "open". Never DOWNGRADE a previously
        # fired order (re-saving an order that already has fired items must not
        # pull it off the KDS) — only set "open" when nothing has been fired yet.
        already_fired = (
            not is_new
            and (
                invoice.kitchen_sent_at is not None
                or invoice.items.filter(sent_to_kitchen=True).exists()
            )
        )
        if not already_fired:
            invoice.order_status = "open"
            invoice.kitchen_sent_at = None
    invoice.held_label = payload.get("held_label")
    invoice.customer = customer
    if customer:
        invoice.buyer_name = customer.name
        invoice.buyer_phone = customer.phone
    else:
        invoice.buyer_name = payload.get("buyer_name") or invoice.buyer_name
        invoice.buyer_phone = payload.get("buyer_phone") or invoice.buyer_phone
    # Totals from the quote (display only on Floor/KDS; final math is at Charge).
    invoice.subtotal = quote.subtotal.amount
    invoice.discount_total = quote.discount_total.amount
    invoice.tax_total = quote.tax_total.amount
    invoice.grand_total = quote.grand_total.amount
    invoice.save()

    # Replace the item snapshot (re-fire may add/remove lines).
    invoice.items.all().delete()
    for line_no, (line_input, lq) in enumerate(zip(cart_lines, quote.lines), start=1):
        product = Product.objects.for_tenant(tenant_id).get(pk=line_input["product"])
        SaleItem.objects.create(
            invoice=invoice, line_number=line_no, product=product,
            product_name=product.name, product_sku=product.sku,
            hs_code=product.hs_code_id, uom_code=product.uom_id,
            quantity=lq.quantity, unit_price=lq.unit_price.amount,
            cost_price=product.cost_price,
            discount_pct=lq.discount_pct, discount_amount=lq.line_discount.amount,
            tax_rate=lq.tax_rate, tax_amount=lq.tax_amount.amount,
            line_total=lq.line_total.amount,
            modifiers=line_input.get("modifiers") or [],
            course=line_input.get("course"),
            item_note=line_input.get("item_note"),
            # Per-line fired flag: honour what the client sends (it tracks this
            # per cart line), else derive from the action. On a "Send to
            # kitchen" (fire) every line is fired; on a "Save order" a line is
            # fired only if it already was (preserved across the delete+recreate
            # by the client echoing sent_to_kitchen back).
            sent_to_kitchen=bool(line_input.get("sent_to_kitchen", fire)),
        )

    # Audit action reflects fire vs save so the log tells them apart.
    if fire:
        action = "open_order_fire" if is_new else "open_order_refire"
    else:
        action = "open_order_save"
    audit.log(
        tenant_id=tenant_id, user=cashier, entity_type="invoice",
        entity_id=invoice.id, action=action,
        after={"order_type": invoice.order_type, "table": str(table_id) if table_id else None},
        request=request,
    )
    return invoice


@transaction.atomic
def send_to_kitchen(invoice: Invoice, *, user=None, request=None) -> Invoice:
    """Mark a held order as fired to the kitchen and flag its unsent lines.

    Idempotent-friendly: re-firing only flips newly-added (unsent) lines and
    bumps the timestamp, so a 'course 2' fire doesn't re-fire course 1.
    """
    before = {"order_status": invoice.order_status, "kitchen_sent_at": str(invoice.kitchen_sent_at)}

    # Flag any not-yet-fired lines as sent (the terminal prints only these on a
    # KOT; the flag is what makes re-firing incremental).
    invoice.items.filter(sent_to_kitchen=False, is_cancelled=False).update(sent_to_kitchen=True)

    invoice.order_status = "sent_to_kitchen"
    invoice.kitchen_sent_at = timezone.now()
    invoice.save(update_fields=["order_status", "kitchen_sent_at", "updated_at"])

    audit.log(
        tenant_id=invoice.tenant_id, user=user, entity_type="invoice",
        entity_id=invoice.id, action="send_to_kitchen",
        before=before,
        after={"order_status": invoice.order_status, "kitchen_sent_at": str(invoice.kitchen_sent_at)},
        request=request,
    )
    return invoice


@transaction.atomic
def set_order_status(invoice: Invoice, status: str, *, user=None, request=None) -> Invoice:
    """Advance the kitchen status (sent_to_kitchen → ready → served)."""
    before = invoice.order_status
    invoice.order_status = status
    invoice.save(update_fields=["order_status", "updated_at"])
    audit.log(
        tenant_id=invoice.tenant_id, user=user, entity_type="invoice",
        entity_id=invoice.id, action="order_status",
        before={"order_status": before}, after={"order_status": status},
        request=request,
    )
    return invoice


@transaction.atomic
def void_open_order(*, tenant_id, client_uuid, user=None, request=None) -> Invoice | None:
    """Remove an OPEN restaurant order from the book (soft-delete).

    Called when a cashier resumes an open order and removes all its items (an
    empty order is a voided order) — top-POS behaviour. We soft-delete (set
    deleted_at) rather than hard-delete so the audit trail is preserved, which
    also drops it from open_orders_qs (filters deleted_at__isnull=True).

    Idempotent + safe: only voids a row that is STILL held and not yet paid
    (is_held=True). A finalized/paid invoice is never touched — a missing or
    already-finalized order is a no-op (returns None) so a retry never errors.
    """
    # Match open_orders_qs: a restaurant open order is held + carries restaurant
    # context (order_status OR order_type). Do NOT require order_type — a saved
    # order may have none (saved before a type was picked), and it must still be
    # voidable. (The old order_type__isnull=False filter made such orders
    # un-voidable, so they lingered in Open orders forever.)
    from django.db.models import Q
    invoice = (
        Invoice.objects.for_tenant(tenant_id)
        .filter(client_uuid=client_uuid, is_held=True, deleted_at__isnull=True)
        .filter(Q(order_status__isnull=False) | Q(order_type__isnull=False))
        .first()
    )
    if invoice is None:
        return None
    invoice.deleted_at = timezone.now()
    invoice.save(update_fields=["deleted_at", "updated_at"])
    audit.log(
        tenant_id=tenant_id, user=user, entity_type="invoice",
        entity_id=invoice.id, action="open_order_void",
        before={"is_held": True}, after={"deleted_at": str(invoice.deleted_at)},
        request=request,
    )
    return invoice


def open_orders_qs(tenant_id, *, branch_id=None, terminal_id=None):
    """Held (open) restaurant orders for a tenant, optionally one branch.

    "Restaurant open order" = held + carries restaurant context. We key that on
    order_status being set (every order created via the open-order flow gets one:
    "open" when saved, "sent_to_kitchen" when fired). We do NOT require
    order_type — a cashier can Save an order before choosing dine-in/takeaway,
    and it must still show up here. (The old order_type__isnull=False filter
    silently hid such saved orders.)

    Scoped to ONE terminal when terminal_id is given: each till owns its own open
    orders, so Terminal 2's unpaid orders never appear on Terminal 3. (All
    terminals' sales still converge on the Admin invoice list, which is not
    terminal-scoped.) branch_id alone (no terminal) still works for admin/KDS
    views that legitimately want the whole branch.
    """
    from django.db.models import Q
    qs = (
        Invoice.objects.for_tenant(tenant_id)
        .filter(is_held=True, deleted_at__isnull=True)
        .filter(Q(order_status__isnull=False) | Q(order_type__isnull=False))
        .select_related("table", "customer")
        .prefetch_related("items")
        .order_by("kitchen_sent_at", "-id")
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if terminal_id:
        qs = qs.filter(terminal_id=terminal_id)
    return qs
