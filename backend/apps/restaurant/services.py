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

    # A held-order upsert must NEVER touch an already-CHARGED sale. A late or
    # duplicate re-fire (stale tablet UI, network replay) would otherwise flip
    # is_held back on and delete/recreate the paid invoice's line items,
    # corrupting a finalized (possibly fiscalized) sale. Refuse it.
    if invoice is not None and not invoice.is_held:
        from rest_framework.exceptions import ValidationError as _VErr
        raise _VErr({"detail": "This order has already been charged and cannot be reopened."})

    # Optimistic concurrency: if the caller says which version it last saw and the
    # row has moved on since, refuse instead of silently clobbering another
    # waiter's edits. Optional — existing callers that omit it are unaffected.
    if invoice is not None and payload.get("expected_updated_at"):
        from django.utils.dateparse import parse_datetime
        from rest_framework.exceptions import APIException
        expected = parse_datetime(payload["expected_updated_at"])
        if expected is not None and invoice.updated_at.replace(microsecond=0) > expected.replace(microsecond=0):
            class _Conflict(APIException):
                status_code = 409
                default_detail = "This order was changed by someone else. Reload and try again."
                default_code = "conflict"
            raise _Conflict()

    is_new = invoice is None
    if is_new:
        invoice = Invoice(
            tenant_id=tenant_id, branch=branch, terminal=terminal, cashier=cashier,
            client_uuid=client_uuid, invoice_type="sale",
            # A held/open order carries only a temporary ORDER TAG, never a real
            # invoice number — the number is minted at charge. Use the tag the
            # terminal sent; if absent, fall back to a client_uuid-derived tag
            # (NOT next_invoice_number, which would burn an invoice number on a
            # draft and leave gaps in the completed sequence).
            local_invoice_number=(
                payload.get("local_invoice_number") or f"ORD-{str(client_uuid)[:8]}"
            ),
            invoice_date=timezone.localdate(), status="pending_sync",
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

    # The item snapshot is REPLACED on every upsert (a re-fire may add/remove
    # lines), but two per-line facts MUST survive the delete+recreate or the KOT
    # relay breaks:
    #   - sent_to_kitchen: which lines are on the kitchen queue.
    #   - kot_printed_at:  which lines a terminal has already PRINTED — this is
    #     what makes an incremental "course 2" fire print only the NEW lines and
    #     never reprint course 1.
    # A recreated row has no stable client id to match on, so we key on a stable
    # content SIGNATURE (product + modifiers + course) and carry the printed
    # timestamp across. Without this, delete+recreate resets every line to
    # "unprinted" and the relay reprints the whole order on each re-fire.
    def _sig(product_id, modifiers, course) -> tuple:
        mod_names = tuple(sorted((m or {}).get("name", "") for m in (modifiers or [])))
        return (str(product_id), mod_names, course or "")

    # signature -> list of printed timestamps (a MULTISET: two lines of the same
    # dish can both have been printed on different courses).
    printed_before: dict[tuple, list] = {}
    for old in invoice.items.all():
        if old.kot_printed_at is not None:
            printed_before.setdefault(
                _sig(old.product_id, old.modifiers, old.course), []
            ).append(old.kot_printed_at)

    invoice.items.all().delete()
    for line_no, (line_input, lq) in enumerate(zip(cart_lines, quote.lines), start=1):
        product = Product.objects.for_tenant(tenant_id).get(pk=line_input["product"])
        line_modifiers = line_input.get("modifiers") or []
        line_course = line_input.get("course")
        client_sent = bool(line_input.get("sent_to_kitchen", False))
        # Per-line fired flag. Firing (fire=True) sends EVERY line to the kitchen
        # — that's what "Send to kitchen" means, so a client that echoes
        # sent_to_kitchen=false on a fired line does NOT keep it off the queue
        # (the relay reads sent_to_kitchen, so honouring a false here would make
        # the KOT never print). On a Save (fire=False) a line is fired only if it
        # already was, which the client preserves by echoing the flag back.
        sent = True if fire else client_sent
        # Carry a printed timestamp across the recreate ONLY onto a line the client
        # says was ALREADY sent (client_sent) — a genuinely NEW line of the same
        # dish (course 2, echoed sent=false) must stay unprinted so it reprints.
        # Consume each printed stamp once (multiset) so N printed lines of a dish
        # restore onto exactly N previously-sent recreated lines.
        kot_printed = None
        if client_sent:
            bucket = printed_before.get(_sig(product.id, line_modifiers, line_course))
            if bucket:
                kot_printed = bucket.pop()
        SaleItem.objects.create(
            invoice=invoice, line_number=line_no, product=product,
            product_name=product.name, product_sku=product.sku,
            hs_code=product.hs_code_id, uom_code=product.uom_id,
            quantity=lq.quantity, unit_price=lq.unit_price.amount,
            cost_price=product.cost_price,
            discount_pct=lq.discount_pct, discount_amount=lq.line_discount.amount,
            tax_rate=lq.tax_rate, tax_amount=lq.tax_amount.amount,
            line_total=lq.line_total.amount,
            modifiers=line_modifiers,
            course=line_course,
            item_note=line_input.get("item_note"),
            sent_to_kitchen=sent,
            kot_printed_at=kot_printed,
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
        .select_related("table", "customer", "terminal")
        .prefetch_related("items")
        .order_by("kitchen_sent_at", "-id")
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if terminal_id:
        # A till owns its own open orders — PLUS every order fired from a shared
        # "waiter tablet" terminal (is_order_taking_only). Those tablets never
        # charge, so their orders must surface on the branch's cashier tills to be
        # picked up and charged. Without this, a waiter-fired order would be
        # invisible on every till and could never be closed.
        qs = qs.filter(
            Q(terminal_id=terminal_id) | Q(terminal__is_order_taking_only=True)
        )
    return qs
