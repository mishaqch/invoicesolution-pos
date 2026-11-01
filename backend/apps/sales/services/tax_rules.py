"""Payment-method-driven services tax — the single server-side owner.

PRA/Punjab lets a restaurant charge a reduced services rate when the customer
pays by card. TDCP: 8% fully-card, 16% if any cash is in the tender.

This rule used to live only in the clients -- the terminal's payment screen and
admin-web each swapped the rate before sending, and the server trusted whatever
arrived. That made it one bug per client, and two of them were live:

  * the hotel folio checkout has its OWN payment picker and never swapped, so a
    card-paying guest was promised 8% and charged 16%; and
  * any terminal on an older build kept sending 16%.

The money must not depend on which build a shop happens to be running, so the
rate is resolved HERE, after the tender is known and before the cart is priced.
Clients may still preview it; the server decides.

ROOMS ARE EXEMPT. A TDCP room night carries a FIXED declared tax (VIP
8820 base + 1680 tax = 10500/night, ~19.05%) set by the resort's published
tariff. That is an amount, not a percentage we may recompute -- re-rating it
would silently change the advertised room price. Callers mark such lines
`is_room`.
"""

from __future__ import annotations

from decimal import Decimal

# Only these tenders count as "card" for the reduced rate. A wallet
# (easypaisa/jazzcash) or a bank transfer is NOT a card under the PRA rule.
CARD_METHODS = frozenset({"card_credit", "card_debit"})


def is_fully_card(payments) -> bool:
    """True when the ENTIRE bill is settled by card.

    Any cash (or wallet, or cheque) in the tender means the standard rate
    applies to the whole invoice -- the reduced rate is for card-only bills.

    A zero-amount tender is ignored: a Rs 0 card line must never buy the
    discount for an otherwise-cash bill. With no tender at all the answer is
    False, so a quote shown before payment uses the standard rate and the
    customer is never promised a total we then have to raise.
    """
    real = [
        p for p in (payments or [])
        if Decimal(str(p.get("amount") or 0)) > 0
    ]
    if not real:
        return False
    return all(p.get("payment_method") in CARD_METHODS for p in real)


def _norm(rate) -> str:
    """Compare rates by VALUE, so "16", "16.0" and "16.00" are one rate."""
    return str(Decimal(str(rate or 0)).normalize())


def resolve_services_rate(lines, *, tenant, fully_card: bool) -> list[dict]:
    """Return `lines` with each taxable services line set to the rate the
    payment method dictates.

    Conservative by design -- it only ever moves a line BETWEEN the tenant's
    two configured rates:

      * no card rate configured  -> returns the lines untouched (feature off,
        so every other tenant behaves exactly as before);
      * a room line              -> untouched (declared fixed tax, see above);
      * a non-taxable line       -> untouched (an exempt item is never taxed);
      * a custom rate (e.g. 5%)  -> untouched, since it is neither of the two
        configured rates and was therefore set deliberately.

    Never mutates the caller's list or dicts: carts are reused by callers and a
    hidden mutation would corrupt the next quote.
    """
    standard = getattr(tenant, "services_tax_rate_standard", None)
    card = getattr(tenant, "services_tax_rate_card", None)
    if standard is None or card is None:
        return list(lines)  # feature off for this tenant

    target = _norm(card) if fully_card else _norm(standard)
    swappable = {_norm(standard), _norm(card)}
    target_str = str(card if fully_card else standard)

    out: list[dict] = []
    for line in lines:
        line = dict(line)  # copy: never mutate the caller's cart
        if (
            not line.get("is_taxable", True)
            or line.get("is_room")
            or _norm(line.get("tax_rate")) not in swappable
            or _norm(line.get("tax_rate")) == target
        ):
            out.append(line)
            continue
        line["tax_rate"] = target_str
        out.append(line)
    return out
