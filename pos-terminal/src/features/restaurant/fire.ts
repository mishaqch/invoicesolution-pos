/**
 * Shared "fire to kitchen" logic — used by the Send-to-kitchen button AND by
 * the charge flow (auto-send on payment). Fires ONLY lines not yet sent, so
 * dine-in orders already fired during the meal don't double-fire on charge,
 * while takeaway/delivery (or a forgotten dine-in send) still reach the kitchen.
 *
 * Side effects:
 *   1. Creates/updates the SERVER open order (live KDS/Floor) — best-effort.
 *   2. Prints a KOT for the un-fired lines.
 *   3. Marks those lines sent_to_kitchen in the cart (only when they actually
 *      reached the kitchen — server OK or a printed KOT) so a retry is possible.
 *
 * Returns a small result so callers can toast appropriately. A no-op (nothing
 * un-fired) returns { fired: 0 }.
 */

import { useSaleStore, type CartLine } from "@/stores/sale";
import { fireOpenOrder } from "./api";

export interface FireResult {
  fired: number;
  serverOk: boolean;
  printOk: boolean;
  serverErr: string | null;
}

export async function fireUnsentToKitchen(opts: {
  branchId: string | null;
  terminalId: string | null;
  /** Override the cart lines (e.g. the priced lines at checkout). Defaults to
   *  the live cart in the sale store. */
  lines?: CartLine[];
}): Promise<FireResult> {
  const st = useSaleStore.getState();
  const allLines = opts.lines ?? st.lines;
  const unsent = allLines.filter((l) => !l.sent_to_kitchen);
  if (unsent.length === 0) {
    return { fired: 0, serverOk: false, printOk: false, serverErr: null };
  }

  // 1) Server open order (full snapshot so KDS shows everything).
  let serverOk = false;
  let serverErr: string | null = null;
  if (!opts.branchId || !opts.terminalId) {
    serverErr = "terminal not paired to a branch";
  } else {
    try {
      await fireOpenOrder({
        client_uuid: st.clientUuid,
        terminal: opts.terminalId,
        branch: opts.branchId,
        order_type: st.orderType,
        table: st.tableId,
        covers: st.covers,
        buyer_name: st.customer?.name ?? null,
        buyer_phone: st.customer?.phone ?? null,
        cart_discount_pct: st.cartDiscountPct,
        cart_lines: allLines.map((l) => ({
          product: l.product_id,
          quantity: l.quantity,
          unit_price: l.unit_price,
          discount_pct: l.discount_pct,
          discount_amount: l.discount_amount,
          tax_rate: l.tax_rate,
          is_taxable: l.is_taxable,
          modifiers: l.modifiers ?? [],
          item_note: l.item_note ?? null,
          course: l.course ?? null,
        })),
      });
      serverOk = true;
    } catch (err) {
      serverErr = err instanceof Error ? err.message : "network error";
    }
  }

  // 2) Print a KOT for the un-fired lines.
  let printOk = false;
  try {
    const now = new Date();
    const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const res = await window.api.printer.printKOT({
      order_number: st.clientUuid.slice(0, 8),
      order_type: st.orderType ?? "dine_in",
      table_name: st.tableName,
      covers: st.covers,
      time,
      items: unsent.map((l) => ({
        product_name: l.product_name,
        quantity: l.quantity,
        modifiers: (l.modifiers ?? []).map((m) => ({ name: m.name })),
        item_note: l.item_note ?? null,
      })),
      width: 48,
    });
    printOk = res.success;
  } catch {
    /* printer error — KOT goes to disk via the main-process fallback */
  }

  // 3) Mark fired only when the kitchen actually got them.
  if (serverOk || printOk) {
    const update = useSaleStore.getState().updateLine;
    unsent.forEach((l) => update(l.id, { sent_to_kitchen: true }));
  }

  return { fired: unsent.length, serverOk, printOk, serverErr };
}
