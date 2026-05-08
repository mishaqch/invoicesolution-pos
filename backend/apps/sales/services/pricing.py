"""Pricing math for a cart.

Inputs:
  cart_lines: list of {product, quantity, unit_price, discount_pct,
                       discount_amount, tax_rate, is_taxable}
  cart_discount_pct: optional cart-level discount (applied AFTER line totals).

Outputs:
  per-line: net_after_discount, tax_amount, line_total
  cart: subtotal, discount_total, tax_total, grand_total

Tax math: per-line round to 4dp, then sum to grand total. Display rounding
to 2dp happens at the receipt layer, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from core.money import Money, sum_money


@dataclass
class LineQuote:
    quantity: Decimal
    unit_price: Money
    discount_pct: Decimal     # 0–100
    discount_amount: Money    # absolute discount in addition to pct
    tax_rate: Decimal         # 0–100; ignored if not is_taxable
    is_taxable: bool

    # Derived
    gross: Money               # quantity * unit_price (before discounts)
    line_discount: Money       # total discount on this line
    net: Money                 # gross - line_discount
    tax_amount: Money          # tax on net
    line_total: Money          # net + tax


@dataclass
class CartQuote:
    lines: list[LineQuote]
    subtotal: Money            # sum of line gross
    line_discount_total: Money
    cart_discount_amount: Money
    discount_total: Money      # line_discount_total + cart_discount_amount
    tax_total: Money
    grand_total: Money


def quote_line(
    *,
    quantity: Decimal | str,
    unit_price: Money | Decimal | str,
    discount_pct: Decimal | str = 0,
    discount_amount: Money | Decimal | str = 0,
    tax_rate: Decimal | str = 0,
    is_taxable: bool = True,
) -> LineQuote:
    qty = Decimal(str(quantity))
    up = unit_price if isinstance(unit_price, Money) else Money.from_str(unit_price)
    pct = Decimal(str(discount_pct))
    amt = discount_amount if isinstance(discount_amount, Money) else Money.from_str(discount_amount)
    rate = Decimal(str(tax_rate))

    gross = up * qty
    pct_disc = Money.from_str(gross.amount * (pct / Decimal(100)))
    line_discount = pct_disc + amt
    net = gross - line_discount
    if net.is_negative():
        net = Money.zero()
        line_discount = gross  # clamp

    tax_amount = (
        Money.from_str(net.amount * (rate / Decimal(100))) if is_taxable else Money.zero()
    )
    line_total = net + tax_amount

    return LineQuote(
        quantity=qty, unit_price=up, discount_pct=pct, discount_amount=amt,
        tax_rate=rate, is_taxable=is_taxable,
        gross=gross, line_discount=line_discount, net=net,
        tax_amount=tax_amount, line_total=line_total,
    )


_QUOTE_LINE_KEYS = {
    "quantity", "unit_price", "discount_pct", "discount_amount",
    "tax_rate", "is_taxable",
}


def quote_cart(
    lines: Iterable[dict],
    *,
    cart_discount_pct: Decimal | str = 0,
    cart_discount_amount: Money | Decimal | str = 0,
) -> CartQuote:
    # Extract only the pricing-relevant fields; cart-line dicts often carry
    # extra keys like `product`, `variant`, `batch` for the persistence layer.
    quoted = [
        quote_line(**{k: v for k, v in line.items() if k in _QUOTE_LINE_KEYS})
        for line in lines
    ]

    subtotal = sum_money(q.gross for q in quoted)
    line_discount_total = sum_money(q.line_discount for q in quoted)
    pre_cart_discount_net = sum_money(q.net for q in quoted)

    cart_pct = Decimal(str(cart_discount_pct))
    cart_pct_amount = Money.from_str(pre_cart_discount_net.amount * (cart_pct / Decimal(100)))
    cart_amount = (
        cart_discount_amount if isinstance(cart_discount_amount, Money)
        else Money.from_str(cart_discount_amount)
    )
    cart_discount = cart_pct_amount + cart_amount

    if cart_discount > pre_cart_discount_net:
        cart_discount = pre_cart_discount_net  # clamp

    # Re-distribute the cart discount proportionally across lines for tax math.
    # This isn't strictly required for the cart total below, but the per-line
    # values returned in CartQuote should remain coherent with the receipt.
    # Phase 2 simplification: cart-level discount reduces post-tax grand total
    # rather than re-running tax calc. Tax law in Pakistan permits both;
    # we'll revisit if FBR rejects this in Phase 4 sandbox testing.

    tax_total = sum_money(q.tax_amount for q in quoted)
    pre_cart_grand = pre_cart_discount_net + tax_total
    grand_total = pre_cart_grand - cart_discount

    return CartQuote(
        lines=quoted,
        subtotal=subtotal,
        line_discount_total=line_discount_total,
        cart_discount_amount=cart_discount,
        discount_total=line_discount_total + cart_discount,
        tax_total=tax_total,
        grand_total=grand_total,
    )
