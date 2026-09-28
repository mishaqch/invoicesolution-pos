import type { CartLine, OrderDraft } from "@/types";
import type { UpsertOrderBody } from "@/api/restaurant";

/** Server order_type strings expected by the backend. Our union already uses
 *  the backend's own values (dine_in / takeaway / delivery). */
export function buildUpsertBody(
  draft: OrderDraft,
  opts: { branch: string; terminal: string; fire: boolean },
): UpsertOrderBody {
  return {
    client_uuid: draft.clientUuid as string,
    branch: opts.branch,
    terminal: opts.terminal,
    order_type: draft.orderType,
    table: draft.tableId ?? null,
    covers: draft.covers,
    held_label: draft.heldLabel ?? null,
    // Echo sent_to_kitchen per line so partially-fired orders keep their
    // locked quantities on the server.
    cart_lines: draft.lines.map((l: CartLine) => ({
      product: l.product,
      quantity: l.quantity,
      unit_price: l.unit_price,
      // Forward tax so the server's held-order totals include it (matches the
      // POS terminal's fire). A null tax_rate means untaxed → is_taxable false.
      tax_rate: l.tax_rate ?? 0,
      is_taxable: l.tax_rate != null,
      modifiers: (l.modifiers ?? []) as Array<Record<string, unknown>>,
      item_note: l.item_note ?? "",
      course: l.course ?? null,
      sent_to_kitchen: l.sent_to_kitchen,
    })),
    fire: opts.fire,
  };
}

/** Running totals (display only). TDCP shows 16% PST but does not submit it. */
export function orderTotals(lines: CartLine[], taxRate = 0.16) {
  const subtotal = lines.reduce((a, l) => a + l.unit_price * l.quantity, 0);
  const tax = Math.round(subtotal * taxRate);
  return { subtotal, tax, grand: subtotal + tax };
}
