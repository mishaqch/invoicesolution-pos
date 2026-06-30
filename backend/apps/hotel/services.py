"""Guest-folio services — open a stay, append daily charges, checkout.

A folio groups normal sales.Invoice rows (one per charge entry) and produces a
consolidated bill at checkout. Room nights are auto-charged on open; restaurant
items are appended via add_charge. Room tax is a FIXED AMOUNT per night, fed to
the percentage-based pricing engine as an exact equivalent rate so the existing
checkout/sync path stays unchanged.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.sales.services.checkout import create_invoice
from apps.sales.services.numbering import next_invoice_number
from apps.tenants.models import Branch, Terminal

from .models import FolioInvoice, GuestFolio, Room


def compute_nights(check_in: dt.datetime, check_out: dt.datetime | None) -> int:
    """Number of billable nights — by calendar night, min 1.

    Jun 30 evening → Jul 10 morning = 10 nights. We count the difference in
    DATES (drop the time-of-day) and clamp to at least 1 (same-day = 1 night).
    """
    if not check_out:
        return 1
    nights = (check_out.date() - check_in.date()).days
    return max(1, nights)


def _room_tax_rate(room: Room) -> Decimal:
    """Convert the room's FIXED nightly tax amount into the equivalent % rate so
    the percentage-based pricing engine yields exactly that amount on the base.
    e.g. base 8820, tax 1680 → 19.0476...% → on 8820 = 1680 exactly."""
    base = room.nightly_base or Decimal("0")
    tax = room.nightly_tax or Decimal("0")
    if base <= 0 or tax <= 0:
        return Decimal("0")
    return (tax / base) * Decimal("100")


@transaction.atomic
def open_stay(
    *,
    tenant_id,
    branch: Branch,
    terminal: Terminal,
    cashier,
    cash_session,
    guest_name: str,
    guest_cnic: str,
    guest_phone: str,
    room: Room,
    check_in: dt.datetime | None = None,
    expected_check_out: dt.datetime | None = None,
    guest_email: str = "",
    guest_address: str = "",
    notes: str = "",
    client_uuid=None,
) -> GuestFolio:
    """Open a folio: validate the room is free, create the folio, and auto-post
    the room-night charge (nights × nightly_base, with the fixed nightly tax)."""
    if room.status == "occupied":
        raise ValidationError({"room": f"Room {room.room_number} is already occupied."})
    if room.product_id is None:
        raise ValidationError({"room": f"Room {room.room_number} has no linked product."})

    check_in = check_in or timezone.now()
    nights = compute_nights(check_in, expected_check_out)

    folio = GuestFolio.objects.create(
        tenant_id=tenant_id,
        branch=branch,
        folio_number=GuestFolio.next_number(tenant_id=tenant_id, branch=branch),
        guest_name=guest_name,
        guest_cnic=guest_cnic,
        guest_phone=guest_phone,
        guest_email=guest_email or "",
        guest_address=guest_address or "",
        room=room,
        check_in=check_in,
        expected_check_out=expected_check_out,
        nights=nights,
        status="open",
        opened_by=cashier,
        notes=notes or "",
    )

    # Mark the room occupied.
    room.status = "occupied"
    room.save(update_fields=["status", "updated_at"])

    # Auto-post the room-night charge as the folio's first charge-invoice.
    _post_room_charge(
        folio=folio, room=room, nights=nights, terminal=terminal,
        cashier=cashier, cash_session=cash_session,
    )
    return folio


def _post_room_charge(*, folio, room, nights, terminal, cashier, cash_session):
    """Create the room-night charge-invoice (held, no payment yet)."""
    rate = _room_tax_rate(room)
    line = {
        "product": str(room.product_id),
        "quantity": str(nights),
        "unit_price": str(room.nightly_base),
        "tax_rate": str(rate),
        "is_taxable": rate > 0,
        "discount_amount": "0",
        "item_note": f"Room {room.room_number} · {nights} night(s)",
    }
    invoice = create_invoice(
        tenant_id=folio.tenant_id,
        branch=folio.branch,
        terminal=terminal,
        cashier=cashier,
        cash_session=cash_session,
        customer=None,
        cart_lines=[line],
        payments=[],                 # unpaid — settled at checkout
        client_uuid=uuid4(),
        local_invoice_number=next_invoice_number(terminal=terminal),
        notes=f"Folio {folio.folio_number} — room charge",
    )
    _hold_and_link(invoice=invoice, folio=folio, kind="room")
    return invoice


@transaction.atomic
def add_charge(
    *,
    folio: GuestFolio,
    terminal: Terminal,
    cashier,
    cash_session,
    cart_lines: list[dict],
    kind: str = "restaurant",
    charge_date: dt.date | None = None,
    client_uuid=None,
) -> "FolioInvoice":
    """Append a charge entry (e.g. today's restaurant order) to an open folio."""
    if folio.status != "open":
        raise ValidationError({"folio": "This folio is not open — cannot add charges."})
    if not cart_lines:
        raise ValidationError({"cart_lines": "No items to charge."})

    invoice = create_invoice(
        tenant_id=folio.tenant_id,
        branch=folio.branch,
        terminal=terminal,
        cashier=cashier,
        cash_session=cash_session,
        customer=None,
        cart_lines=cart_lines,
        payments=[],                 # unpaid — settled at checkout
        client_uuid=client_uuid or uuid4(),
        local_invoice_number=next_invoice_number(terminal=terminal),
        notes=f"Folio {folio.folio_number} — {kind} charge",
    )
    link = _hold_and_link(
        invoice=invoice, folio=folio, kind=kind,
        charge_date=charge_date or timezone.localdate(),
    )
    return link


def _hold_and_link(*, invoice, folio, kind, charge_date=None) -> FolioInvoice:
    """Mark the charge-invoice held (it isn't a standalone settled sale) and link
    it to the folio."""
    invoice.is_held = True
    invoice.held_label = f"Folio {folio.folio_number}"
    invoice.save(update_fields=["is_held", "held_label", "updated_at"])
    return FolioInvoice.objects.create(
        tenant_id=folio.tenant_id,
        folio=folio,
        invoice=invoice,
        kind=kind,
        charge_date=charge_date or timezone.localdate(),
    )


@transaction.atomic
def checkout_stay(
    *,
    folio: GuestFolio,
    payments: list[dict],
    cashier,
    check_out: dt.datetime | None = None,
) -> GuestFolio:
    """Close the folio: finalize all charge-invoices, record the settlement
    payment(s) against the room (anchor) invoice, free the room."""
    if folio.status != "open":
        raise ValidationError({"folio": "This folio is already closed."})

    folio = GuestFolio.objects.select_for_update().get(pk=folio.pk)
    check_out = check_out or timezone.now()

    charges = list(folio.charges.select_related("invoice").all())
    if not charges:
        raise ValidationError({"folio": "Folio has no charges to settle."})

    # Un-hold every charge-invoice so they become finalized records (each keeps
    # its own number + items; they stay non-fiscal for TDCP). Payment is recorded
    # against the anchor (room) invoice to represent the single settlement.
    from apps.payments.adapters import get_adapter

    anchor = None
    for ch in charges:
        inv = ch.invoice
        inv.is_held = False
        inv.held_label = None
        inv.save(update_fields=["is_held", "held_label", "updated_at"])
        if ch.kind == "room" and anchor is None:
            anchor = inv
    anchor = anchor or charges[0].invoice

    # Record settlement payments on the anchor invoice. The adapter creates the
    # Payment rows; we also bump the anchor's denormalized paid_total so the
    # consolidated bill reflects what was settled (the adapter doesn't do this).
    settled = Decimal("0")
    for p in payments or []:
        amount = Decimal(str(p["amount"]))
        adapter = get_adapter(p["payment_method"])
        adapter.record_payment(invoice=anchor, amount=amount, data=p, user=cashier)
        settled += amount
    if settled:
        anchor.paid_total = (anchor.paid_total or Decimal("0")) + settled
        anchor.save(update_fields=["paid_total", "updated_at"])

    # Free the room + close the folio.
    if folio.room:
        folio.room.status = "available"
        folio.room.save(update_fields=["status", "updated_at"])

    folio.status = "closed"
    folio.check_out = check_out
    folio.closed_at = timezone.now()
    folio.save(update_fields=["status", "check_out", "closed_at", "updated_at"])
    return folio


def consolidated_bill(folio: GuestFolio) -> dict:
    """Structured consolidated bill for the whole stay — guest, room, nights,
    every charge grouped by date, and totals (room + restaurant tax split)."""
    charges = (
        folio.charges.select_related("invoice")
        .prefetch_related("invoice__items")
        .order_by("charge_date", "created_at")
    )

    days: dict[str, list] = {}
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    grand_total = Decimal("0")
    paid_total = Decimal("0")

    for ch in charges:
        inv = ch.invoice
        day = ch.charge_date.isoformat()
        items = []
        for it in inv.items.all():
            if it.is_cancelled:
                continue
            items.append({
                "name": it.product_name,
                "quantity": str(it.quantity),
                "unit_price": str(it.unit_price),
                "tax_amount": str(it.tax_amount),
                "line_total": str(it.line_total),
                "note": it.item_note or "",
            })
        days.setdefault(day, []).append({
            "kind": ch.kind,
            "invoice_number": inv.local_invoice_number,
            "items": items,
            "subtotal": str(inv.subtotal),
            "tax": str(inv.tax_total),
            "total": str(inv.grand_total),
        })
        subtotal += inv.subtotal or Decimal("0")
        tax_total += inv.tax_total or Decimal("0")
        grand_total += inv.grand_total or Decimal("0")
        paid_total += inv.paid_total or Decimal("0")

    return {
        "folio_number": folio.folio_number,
        "status": folio.status,
        "guest": {
            "name": folio.guest_name,
            "cnic": folio.guest_cnic,
            "phone": folio.guest_phone,
            "email": folio.guest_email,
            "address": folio.guest_address,
        },
        "room": (
            {
                "number": folio.room.room_number,
                "type": folio.room.room_type,
                "nightly_total": str(folio.room.nightly_total),
            } if folio.room else None
        ),
        "check_in": folio.check_in.isoformat() if folio.check_in else None,
        "check_out": folio.check_out.isoformat() if folio.check_out else None,
        "expected_check_out": (
            folio.expected_check_out.isoformat() if folio.expected_check_out else None
        ),
        "nights": folio.nights,
        "days": [{"date": d, "charges": c} for d, c in sorted(days.items())],
        "subtotal": str(subtotal),
        "tax_total": str(tax_total),
        "grand_total": str(grand_total),
        "paid_total": str(paid_total),
        "balance": str(grand_total - paid_total),
    }
