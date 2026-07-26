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
    room: Room | None = None,
    rooms: list[dict] | None = None,
    check_in: dt.datetime | None = None,
    expected_check_out: dt.datetime | None = None,
    guest_email: str = "",
    guest_address: str = "",
    partner_name: str = "",
    partner_cnic: str = "",
    notes: str = "",
    client_uuid=None,
) -> GuestFolio:
    """Open a folio for ONE guest booking one OR MANY rooms.

    Pass either `room=` (single) or `rooms=` (list of dicts:
    {room, check_in?, expected_check_out?}). Each room is validated free,
    marked occupied, recorded on a FolioRoom, and auto-charged its own nights
    (nights × nightly_base + fixed nightly tax), tagged to that room so the
    consolidated bill can group charges per room.
    """
    default_ci = check_in or timezone.now()

    # Normalise to a list of {room, check_in, expected_check_out}.
    booked: list[dict] = []
    if rooms:
        for r in rooms:
            booked.append({
                "room": r["room"],
                "check_in": r.get("check_in") or default_ci,
                "expected_check_out": r.get("expected_check_out") or expected_check_out,
            })
    elif room is not None:
        booked.append({"room": room, "check_in": default_ci, "expected_check_out": expected_check_out})
    if not booked:
        raise ValidationError({"rooms": "At least one room is required."})

    for b in booked:
        rm: Room = b["room"]
        if rm.status == "occupied":
            raise ValidationError({"room": f"Room {rm.room_number} is already occupied."})
        if rm.product_id is None:
            raise ValidationError({"room": f"Room {rm.room_number} has no linked product."})

    primary = booked[0]["room"]
    primary_nights = compute_nights(booked[0]["check_in"], booked[0]["expected_check_out"])

    folio = GuestFolio.objects.create(
        tenant_id=tenant_id,
        branch=branch,
        folio_number=GuestFolio.next_number(tenant_id=tenant_id, branch=branch),
        guest_name=guest_name,
        guest_cnic=guest_cnic,
        guest_phone=guest_phone,
        guest_email=guest_email or "",
        guest_address=guest_address or "",
        partner_name=partner_name or "",
        partner_cnic=partner_cnic or "",
        room=primary,                 # primary room (backward compat + summary)
        check_in=booked[0]["check_in"],
        expected_check_out=booked[0]["expected_check_out"],
        nights=primary_nights,
        status="open",
        opened_by=cashier,
        notes=notes or "",
    )

    from .models import FolioRoom
    for b in booked:
        rm = b["room"]
        n = compute_nights(b["check_in"], b["expected_check_out"])
        FolioRoom.objects.create(
            tenant_id=tenant_id, folio=folio, room=rm, nights=n,
            check_in=b["check_in"], expected_check_out=b["expected_check_out"],
        )
        rm.status = "occupied"
        rm.save(update_fields=["status", "updated_at"])
        _post_room_charge(
            folio=folio, room=rm, nights=n, terminal=terminal,
            cashier=cashier, cash_session=cash_session,
        )
    return folio


def _post_room_charge(*, folio, room, nights, terminal, cashier, cash_session):
    """Create the room-night charge-invoice (held, no payment yet), tagged to
    the room so multi-room bills group correctly."""
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
        notes=f"Folio {folio.folio_number} — room charge ({room.room_number})",
    )
    _hold_and_link(invoice=invoice, folio=folio, kind="room", room=room)
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
    room: Room | None = None,
    client_uuid=None,
) -> "FolioInvoice":
    """Append a charge entry (e.g. today's restaurant order) to an open folio.

    `room` optionally tags the charge to one of the folio's booked rooms (so a
    multi-room bill groups food/other charges under the right room). NULL = a
    general charge for the whole stay.
    """
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
        invoice=invoice, folio=folio, kind=kind, room=room,
        charge_date=charge_date or timezone.localdate(),
    )
    return link


def _hold_and_link(*, invoice, folio, kind, charge_date=None, room=None) -> FolioInvoice:
    """Mark the charge-invoice held (it isn't a standalone settled sale) and link
    it to the folio, optionally tagged to a specific room."""
    invoice.is_held = True
    invoice.held_label = f"Folio {folio.folio_number}"
    invoice.save(update_fields=["is_held", "held_label", "updated_at"])
    return FolioInvoice.objects.create(
        tenant_id=folio.tenant_id,
        folio=folio,
        invoice=invoice,
        kind=kind,
        room=room,
        charge_date=charge_date or timezone.localdate(),
    )


def _recompute_invoice_totals(invoice) -> None:
    """Recompute an invoice's stored money totals from its NON-cancelled items.

    After voiding an item on a folio charge, the invoice's subtotal/tax/grand
    must drop accordingly (the consolidated bill sums these stored totals).
    Rooms use a fixed tax amount baked into each item's tax_amount, so summing
    per-item tax_amount is exact for both room and food lines.
    """
    live = [it for it in invoice.items.all() if not it.is_cancelled]
    subtotal = sum((it.line_total - it.tax_amount for it in live), Decimal("0"))
    tax_total = sum((it.tax_amount for it in live), Decimal("0"))
    grand = sum((it.line_total for it in live), Decimal("0"))
    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.grand_total = grand
    invoice.save(update_fields=["subtotal", "tax_total", "grand_total", "updated_at"])


@transaction.atomic
def void_item(*, folio: GuestFolio, charge, sale_item_id, user=None) -> "FolioInvoice":
    """Void ONE item on a folio charge (open folio only). Audit-don't-delete:
    the item is marked cancelled (kept for the record), excluded from totals."""
    if folio.status != "open":
        raise ValidationError({"folio": "Can only edit charges on an open stay."})
    if charge.folio_id != folio.id:
        raise ValidationError({"charge": "Charge does not belong to this folio."})

    invoice = charge.invoice
    try:
        item = invoice.items.get(pk=sale_item_id)
    except invoice.items.model.DoesNotExist:
        raise ValidationError({"item": "Item not found on this charge."})
    if item.is_cancelled:
        raise ValidationError({"item": "Item already removed."})

    item.is_cancelled = True
    item.cancelled_at = timezone.now()
    item.save(update_fields=["is_cancelled", "cancelled_at"])
    _recompute_invoice_totals(invoice)

    from apps.audit.services import log as audit_log
    audit_log(
        tenant_id=folio.tenant_id, user=user,
        entity_type="sale_item", entity_id=item.id, action="cancel",
        after={"folio": folio.folio_number, "reason": "folio_item_void"},
    )
    return charge


@transaction.atomic
def void_charge(*, folio: GuestFolio, charge, user=None) -> None:
    """Void an ENTIRE charge entry (open folio only). Every item is cancelled,
    the charge is unlinked from the folio, and the (now-empty) invoice is
    soft-cancelled. History is preserved."""
    if folio.status != "open":
        raise ValidationError({"folio": "Can only edit charges on an open stay."})
    if charge.folio_id != folio.id:
        raise ValidationError({"charge": "Charge does not belong to this folio."})
    if charge.kind == "room":
        raise ValidationError(
            {"charge": "The room charge can't be removed — check out or cancel the stay instead."}
        )

    invoice = charge.invoice
    now = timezone.now()
    for it in invoice.items.all():
        if not it.is_cancelled:
            it.is_cancelled = True
            it.cancelled_at = now
            it.save(update_fields=["is_cancelled", "cancelled_at"])
    _recompute_invoice_totals(invoice)
    invoice.status = "cancelled"
    invoice.save(update_fields=["status", "updated_at"])

    from apps.audit.services import log as audit_log
    audit_log(
        tenant_id=folio.tenant_id, user=user,
        entity_type="invoice", entity_id=invoice.id, action="cancel",
        after={"folio": folio.folio_number, "reason": "folio_charge_void"},
    )
    # Unlink from the folio so it no longer appears on the bill.
    charge.delete()


# ---------------------------------------------------------------------------
# Edit / update a stay
# ---------------------------------------------------------------------------

# Guest fields a cashier may edit on an open stay (typo fixes etc.).
_EDITABLE_GUEST_FIELDS = {
    "guest_name": "guest_name",
    "guest_cnic": "guest_cnic",
    "guest_phone": "guest_phone",
    "guest_email": "guest_email",
    "guest_address": "guest_address",
    "partner_name": "partner_name",
    "partner_cnic": "partner_cnic",
    "notes": "notes",
}


@transaction.atomic
def update_stay(
    *,
    folio: GuestFolio,
    fields: dict,
    check_in: dt.datetime | None = None,
    expected_check_out: dt.datetime | None = None,
    terminal: Terminal | None = None,
    cashier=None,
    cash_session=None,
    user=None,
) -> GuestFolio:
    """Edit an OPEN stay's guest details and/or dates.

    Guest details are updated in place. If dates change, every booked room's
    nights are recomputed and its room charge is re-posted at the new nights
    (old room charge voided, audit-kept) so the bill stays correct.
    """
    # Reload under lock FIRST, then check status — the caller may hold a stale
    # in-memory copy whose status predates a checkout/cancel.
    folio = GuestFolio.objects.select_for_update().get(pk=folio.pk)
    if folio.status != "open":
        raise ValidationError({"folio": "Can only edit an open stay."})

    before = {}
    changed_fields = []
    for key, model_field in _EDITABLE_GUEST_FIELDS.items():
        if key in fields and fields[key] is not None:
            new_val = fields[key]
            old_val = getattr(folio, model_field)
            if old_val != new_val:
                before[model_field] = old_val
                setattr(folio, model_field, new_val)
                changed_fields.append(model_field)
    if changed_fields:
        folio.save(update_fields=[*changed_fields, "updated_at"])

    dates_changed = check_in is not None or expected_check_out is not None
    if dates_changed:
        # Re-posting the room charge needs a terminal (for invoice numbering).
        # The cash session may be None — the room charge is held/unpaid until
        # checkout, same as on open_stay.
        if terminal is None:
            raise ValidationError(
                {"dates": "Editing dates needs an active till (terminal)."}
            )
        new_ci = check_in or folio.check_in or timezone.now()
        new_co = expected_check_out if expected_check_out is not None else folio.expected_check_out
        _reprice_room_nights(
            folio=folio, check_in=new_ci, expected_check_out=new_co,
            terminal=terminal, cashier=cashier or user, cash_session=cash_session,
        )
        folio.check_in = new_ci
        folio.expected_check_out = new_co
        folio.nights = compute_nights(new_ci, new_co)
        folio.save(update_fields=["check_in", "expected_check_out", "nights", "updated_at"])

    from apps.audit.services import log as audit_log
    audit_log(
        tenant_id=folio.tenant_id, user=user,
        entity_type="guest_folio", entity_id=folio.id, action="update",
        before=before or None,
        after={"folio": folio.folio_number, "dates_changed": dates_changed},
    )
    return folio


def _reprice_room_nights(*, folio, check_in, expected_check_out, terminal, cashier, cash_session):
    """Recompute nights for each booked room and re-post its room charge.

    The old room-night charge for each room is voided (items cancelled, invoice
    soft-cancelled, kept for audit) and a fresh one posted at the new nights.
    """
    from .models import FolioRoom

    booked = list(folio.rooms_booked.select_related("room").all())
    if not booked:
        # Legacy single-room folio with no FolioRoom rows.
        if folio.room_id:
            booked = [_LegacyBooked(folio.room)]
        else:
            return

    now = timezone.now()
    for fr in booked:
        room = fr.room
        new_nights = compute_nights(check_in, expected_check_out)
        # Void the existing room charge for THIS room (if any).
        old = (
            FolioInvoice.objects.for_tenant(folio.tenant_id)
            .filter(folio=folio, kind="room", room=room)
            .select_related("invoice").first()
        )
        if old is not None:
            inv = old.invoice
            for it in inv.items.all():
                if not it.is_cancelled:
                    it.is_cancelled = True
                    it.cancelled_at = now
                    it.save(update_fields=["is_cancelled", "cancelled_at"])
            _recompute_invoice_totals(inv)
            inv.status = "cancelled"
            inv.save(update_fields=["status", "updated_at"])
            old.delete()
        # Re-post at the new nights.
        _post_room_charge(
            folio=folio, room=room, nights=new_nights, terminal=terminal,
            cashier=cashier, cash_session=cash_session,
        )
        # Keep the FolioRoom night count in step (real rows only).
        if isinstance(fr, _LegacyBooked):
            continue
        fr.nights = new_nights
        fr.check_in = check_in
        fr.expected_check_out = expected_check_out
        fr.save(update_fields=["nights", "check_in", "expected_check_out"])


class _LegacyBooked:
    """Shim so _reprice_room_nights can treat a legacy single-room folio (no
    FolioRoom rows) the same as a multi-room one."""
    def __init__(self, room):
        self.room = room


@transaction.atomic
def add_room_to_stay(
    *, folio: GuestFolio, room: Room, terminal: Terminal, cashier, cash_session,
    check_in: dt.datetime | None = None, expected_check_out: dt.datetime | None = None,
    user=None,
) -> GuestFolio:
    """Add another room to an OPEN stay (same guest). Posts its room charge."""
    folio = GuestFolio.objects.select_for_update().get(pk=folio.pk)
    if folio.status != "open":
        raise ValidationError({"folio": "Can only edit an open stay."})
    if room.status == "occupied":
        raise ValidationError({"room": f"Room {room.room_number} is already occupied."})
    if room.product_id is None:
        raise ValidationError({"room": f"Room {room.room_number} has no linked product."})
    if folio.rooms_booked.filter(room=room).exists():
        raise ValidationError({"room": f"Room {room.room_number} is already on this stay."})

    ci = check_in or folio.check_in or timezone.now()
    co = expected_check_out if expected_check_out is not None else folio.expected_check_out
    nights = compute_nights(ci, co)

    from .models import FolioRoom
    FolioRoom.objects.create(
        tenant_id=folio.tenant_id, folio=folio, room=room, nights=nights,
        check_in=ci, expected_check_out=co,
    )
    room.status = "occupied"
    room.save(update_fields=["status", "updated_at"])
    _post_room_charge(
        folio=folio, room=room, nights=nights, terminal=terminal,
        cashier=cashier, cash_session=cash_session,
    )

    from apps.audit.services import log as audit_log
    audit_log(
        tenant_id=folio.tenant_id, user=user,
        entity_type="guest_folio", entity_id=folio.id, action="update",
        after={"folio": folio.folio_number, "added_room": room.room_number},
    )
    return folio


@transaction.atomic
def remove_room_from_stay(*, folio: GuestFolio, room: Room, user=None) -> GuestFolio:
    """Remove a room from an OPEN multi-room stay: void its room charge, free the
    room. Refuses to remove the last room (cancel the whole stay instead)."""
    folio = GuestFolio.objects.select_for_update().get(pk=folio.pk)
    if folio.status != "open":
        raise ValidationError({"folio": "Can only edit an open stay."})

    booked = list(folio.rooms_booked.select_related("room").all())
    if not any(fr.room_id == room.id for fr in booked):
        raise ValidationError({"room": "That room is not on this stay."})
    if len(booked) <= 1:
        raise ValidationError(
            {"room": "This is the only room — cancel the whole stay instead."}
        )

    now = timezone.now()
    # Void every charge tagged to this room (room-night AND any food tagged to it).
    tagged = (
        FolioInvoice.objects.for_tenant(folio.tenant_id)
        .filter(folio=folio, room=room).select_related("invoice")
    )
    for ch in tagged:
        inv = ch.invoice
        for it in inv.items.all():
            if not it.is_cancelled:
                it.is_cancelled = True
                it.cancelled_at = now
                it.save(update_fields=["is_cancelled", "cancelled_at"])
        _recompute_invoice_totals(inv)
        inv.status = "cancelled"
        inv.save(update_fields=["status", "updated_at"])
        ch.delete()

    folio.rooms_booked.filter(room=room).delete()
    room.status = "available"
    room.save(update_fields=["status", "updated_at"])

    # If we removed the primary room, repoint folio.room to a remaining one.
    if folio.room_id == room.id:
        remaining = folio.rooms_booked.select_related("room").first()
        folio.room = remaining.room if remaining else None
        folio.save(update_fields=["room", "updated_at"])

    from apps.audit.services import log as audit_log
    audit_log(
        tenant_id=folio.tenant_id, user=user,
        entity_type="guest_folio", entity_id=folio.id, action="update",
        after={"folio": folio.folio_number, "removed_room": room.room_number},
    )
    return folio


@transaction.atomic
def cancel_stay(*, folio: GuestFolio, reason: str = "", user=None) -> GuestFolio:
    """Cancel an OPEN stay (customer changed their mind, etc.).

    Audit-don't-delete: void every charge (items cancelled, invoices
    soft-cancelled — all kept for the six-year record), free every booked room,
    and mark the folio cancelled. Refuses once the stay is checked out.
    """
    folio = GuestFolio.objects.select_for_update().get(pk=folio.pk)
    if folio.status != "open":
        raise ValidationError({"folio": f"Stay is already {folio.status} — cannot cancel."})

    now = timezone.now()

    # Void ALL charges (including the room charge) — kept for audit.
    for ch in folio.charges.select_related("invoice").all():
        inv = ch.invoice
        for it in inv.items.all():
            if not it.is_cancelled:
                it.is_cancelled = True
                it.cancelled_at = now
                it.save(update_fields=["is_cancelled", "cancelled_at"])
        _recompute_invoice_totals(inv)
        inv.is_held = False
        inv.held_label = None
        inv.status = "cancelled"
        inv.save(update_fields=["is_held", "held_label", "status", "updated_at"])

    # Free every booked room (multi-room), then the legacy single room.
    booked = list(folio.rooms_booked.select_related("room").all())
    if booked:
        for fr in booked:
            fr.room.status = "available"
            fr.room.save(update_fields=["status", "updated_at"])
    elif folio.room:
        folio.room.status = "available"
        folio.room.save(update_fields=["status", "updated_at"])

    folio.status = "cancelled"
    folio.closed_at = now
    if reason:
        folio.notes = (folio.notes + "\n" if folio.notes else "") + f"Cancelled: {reason}"
    folio.save(update_fields=["status", "closed_at", "notes", "updated_at"])

    from apps.audit.services import log as audit_log
    audit_log(
        tenant_id=folio.tenant_id, user=user,
        entity_type="guest_folio", entity_id=folio.id, action="cancel",
        after={"folio": folio.folio_number, "reason": reason or "stay_cancelled"},
    )
    return folio


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

    # Free ALL booked rooms (multi-room folios) + close the folio.
    booked_rooms = list(folio.rooms_booked.select_related("room").all())
    if booked_rooms:
        for fr in booked_rooms:
            fr.room.status = "available"
            fr.room.save(update_fields=["status", "updated_at"])
    elif folio.room:  # legacy single-room folio
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
        folio.charges.select_related("invoice", "room")
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
        ch_sub = Decimal("0")
        ch_tax = Decimal("0")
        ch_total = Decimal("0")
        for it in inv.items.all():
            if it.is_cancelled:
                continue
            items.append({
                "id": str(it.id),
                "name": it.product_name,
                "quantity": str(it.quantity),
                "unit_price": str(it.unit_price),
                "tax_amount": str(it.tax_amount),
                "line_total": str(it.line_total),
                "note": it.item_note or "",
            })
            ch_tax += it.tax_amount or Decimal("0")
            ch_total += it.line_total or Decimal("0")
            ch_sub += (it.line_total or Decimal("0")) - (it.tax_amount or Decimal("0"))
        # Skip a charge whose every item was voided (nothing left to show/bill).
        if not items:
            continue
        days.setdefault(day, []).append({
            "charge_id": str(ch.id),
            "kind": ch.kind,
            "invoice_number": inv.local_invoice_number,
            "room_number": ch.room.room_number if ch.room_id else None,
            "can_remove": ch.kind != "room",   # room charge isn't removable here
            "items": items,
            "subtotal": str(ch_sub),
            "tax": str(ch_tax),
            "total": str(ch_total),
        })
        subtotal += ch_sub
        tax_total += ch_tax
        grand_total += ch_total
        paid_total += inv.paid_total or Decimal("0")

    return {
        "id": str(folio.id),
        "folio_number": folio.folio_number,
        "status": folio.status,
        "guest": {
            "name": folio.guest_name,
            "cnic": folio.guest_cnic,
            "phone": folio.guest_phone,
            "email": folio.guest_email,
            "address": folio.guest_address,
            "partner_name": folio.partner_name,
            "partner_cnic": folio.partner_cnic,
        },
        "room": (
            {
                "number": folio.room.room_number,
                "type": folio.room.room_type,
                "nightly_total": str(folio.room.nightly_total),
            } if folio.room else None
        ),
        # All rooms booked on this folio (multi-room stays). Empty list for a
        # legacy single-room folio that predates FolioRoom.
        "rooms": [
            {
                "id": str(fr.room_id),
                "number": fr.room.room_number,
                "type": fr.room.room_type,
                "nights": fr.nights,
                "nightly_total": str(fr.room.nightly_total),
                "check_in": fr.check_in.isoformat() if fr.check_in else None,
                "expected_check_out": (
                    fr.expected_check_out.isoformat() if fr.expected_check_out else None
                ),
            }
            for fr in folio.rooms_booked.select_related("room").all()
        ],
        "check_in": folio.check_in.isoformat() if folio.check_in else None,
        "check_out": folio.check_out.isoformat() if folio.check_out else None,
        "expected_check_out": (
            folio.expected_check_out.isoformat() if folio.expected_check_out else None
        ),
        "nights": folio.nights,
        "days": [{"date": d, "charges": c} for d, c in sorted(days.items())],
        # Quantize to 4dp so a fully-voided/zero bill reads "0.0000", not "0"
        # — consistent with every non-zero total (the money wire format).
        "subtotal": str(subtotal.quantize(Decimal("0.0001"))),
        "tax_total": str(tax_total.quantize(Decimal("0.0001"))),
        "grand_total": str(grand_total.quantize(Decimal("0.0001"))),
        "paid_total": str(paid_total.quantize(Decimal("0.0001"))),
        "balance": str((grand_total - paid_total).quantize(Decimal("0.0001"))),
    }
