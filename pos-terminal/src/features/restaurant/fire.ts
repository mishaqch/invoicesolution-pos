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
import { fireOpenOrder, voidOpenOrder } from "./api";

/**
 * Return this order's number = the LOCAL INVOICE NUMBER ("KK-T3-2026-0000001").
 * Assigned on the first save/send and cached on the sale store so re-fires, the
 * KOT, the Open-orders card and the final invoice all show the SAME number.
 * Generated from the paired branch/terminal so it matches the server format.
 * Falls back to the client_uuid prefix only if pairing/numbering is unavailable.
 */
async function ensureOrderNumber(): Promise<string> {
  const st = useSaleStore.getState();
  if (st.orderNumber) return st.orderNumber;
  try {
    const s = await window.api.pairing.status();
    const id = s.identity;
    if (id) {
      const n = await window.api.numbering.next({
        branchCode: id.branchCode,
        terminalIndex: id.terminalIndex,
      });
      if (n) {
        useSaleStore.getState().setOrderNumber(n);
        return n;
      }
    }
  } catch {
    /* fall through to the uuid prefix */
  }
  return st.clientUuid.slice(0, 8);
}

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

  // Assign a short daily order number (001, 002…) on the FIRST fire and keep it
  // stable for re-fires. Used on the KOT so the kitchen sees "Order 001", not a
  // hex id. Best-effort — if it fails we fall back to the client_uuid prefix.
  const orderNo = await ensureOrderNumber();

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
        // Default dine_in if unset so the order always shows in Open orders.
        order_type: st.orderType ?? "dine_in",
        table: st.tableId,
        covers: st.covers,
        buyer_name: st.customer?.name ?? null,
        buyer_phone: st.customer?.phone ?? null,
        cart_discount_pct: st.cartDiscountPct,
        local_invoice_number: orderNo,
        fire: true,
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
          sent_to_kitchen: l.sent_to_kitchen ?? false,
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
      order_number: orderNo,
      order_type: st.orderType ?? "dine_in",
      table_name: st.tableName,
      covers: st.covers,
      time,
      // Human reference for the ticket when there's no table (label or walk-in
      // name), so the kitchen sees a meaningful name, not just a hex order id.
      reference: st.heldLabel ?? st.customer?.name ?? null,
      // ADDITIONAL ORDER when some lines were already sent — this is a follow-up
      // fire on the SAME order (same order_number), not a brand-new order.
      is_additional: allLines.some((l) => l.sent_to_kitchen),
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

export interface SaveResult {
  serverOk: boolean;
  serverErr: string | null;
}

/**
 * "Save order" — park the current cart in the server "Open orders" book WITHOUT
 * alerting the kitchen (no KOT print, no KDS entry). This is the top-POS
 * "Save/Send" action: it lets a cashier step away to another table before the
 * customer has finalised, then resume this order later from Open orders.
 *
 * Difference vs fireUnsentToKitchen:
 *   - order_status stays "open" (server-side), so it does NOT show on the KDS.
 *   - no KOT is printed.
 *   - lines are NOT marked sent_to_kitchen (already-fired lines keep their flag).
 *
 * It still upserts the FULL cart snapshot (idempotent on client_uuid), so the
 * order appears in Open orders and its table reads as occupied on the floor.
 */
export async function saveOpenOrder(opts: {
  branchId: string | null;
  terminalId: string | null;
  lines?: CartLine[];
  /** Cashier's reference so the order is recognisable in Open orders (e.g.
   *  "Table 3 / Ahmed", "red shirt guy"). Required by the Save-order button. */
  heldLabel?: string;
}): Promise<SaveResult> {
  const st = useSaleStore.getState();
  const allLines = opts.lines ?? st.lines;
  if (allLines.length === 0) {
    return { serverOk: false, serverErr: "empty cart" };
  }
  if (!opts.branchId || !opts.terminalId) {
    return { serverOk: false, serverErr: "terminal not paired to a branch" };
  }
  // Assign the order number (local invoice number) now so a saved order already
  // carries its final number in Open orders and on the eventual invoice.
  const orderNo = await ensureOrderNumber();
  try {
    await fireOpenOrder({
      client_uuid: st.clientUuid,
      terminal: opts.terminalId,
      branch: opts.branchId,
      // Default to dine_in when the cashier saved before choosing a type — a
      // saved order must always carry an order_type so it shows in Open orders.
      order_type: st.orderType ?? "dine_in",
      table: st.tableId,
      covers: st.covers,
      buyer_name: st.customer?.name ?? null,
      buyer_phone: st.customer?.phone ?? null,
      cart_discount_pct: st.cartDiscountPct,
      local_invoice_number: orderNo,
      held_label: opts.heldLabel ?? null,
      fire: false,
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
        // Preserve any already-fired lines so saving doesn't un-fire them.
        sent_to_kitchen: l.sent_to_kitchen ?? false,
      })),
    });
    return { serverOk: true, serverErr: null };
  } catch (err) {
    return { serverOk: false, serverErr: err instanceof Error ? err.message : "network error" };
  }
}

export interface VoidResult {
  /** Whether this cart was a saved/open order that had to be voided server-side. */
  wasOpenOrder: boolean;
  /** Whether any items had already been sent to the kitchen (→ cancellation KOT). */
  hadFired: boolean;
}

/**
 * Void the current restaurant order: remove it from the server "Open orders"
 * book AND — if any items were already sent to the kitchen — print a loud
 * CANCELLED ticket to the kitchen so the cooks STOP preparing it.
 *
 * Called from the "Void sale" button. Best-effort + safe:
 *   - Only voids server-side when this cart is a resumed OPEN order (it has a
 *     resumedOpenOrderUuid). A fresh, never-saved cart has nothing to void.
 *   - Only prints the cancellation KOT when at least one line was fired.
 *
 * Does NOT clear the cart — the caller (Void button) resets the sale after.
 * (No branch/terminal args needed: the void is keyed on the order's client_uuid
 * and the cancellation KOT resolves the kitchen printer in the main process.)
 */
export async function voidOrderAndNotifyKitchen(): Promise<VoidResult> {
  const st = useSaleStore.getState();
  const openUuid = st.resumedOpenOrderUuid;
  const firedLines = st.lines.filter((l) => l.sent_to_kitchen);
  const hadFired = firedLines.length > 0;

  // 1) Remove the order from the server Open-orders book (soft-delete). Only a
  //    resumed/saved open order needs this; a fresh cart has no server order.
  let wasOpenOrder = false;
  if (openUuid) {
    wasOpenOrder = true;
    await voidOpenOrder(openUuid).catch(() => {}); // best-effort; panel auto-refreshes
  }

  // 2) Kitchen cancellation ticket — ONLY if something was already fired.
  if (hadFired) {
    try {
      const now = new Date();
      const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
      await window.api.printer.printKOT({
        // Same order number the order was fired with, so the cook matches the
        // cancellation to the original ticket.
        order_number: st.orderNumber ?? st.clientUuid.slice(0, 8),
        order_type: st.orderType ?? "dine_in",
        table_name: st.tableName,
        covers: st.covers,
        time,
        reference: st.heldLabel ?? st.customer?.name ?? null,
        is_void: true, // → "*** CANCELLED *** / VOID — DO NOT PREPARE"
        items: firedLines.map((l) => ({
          product_name: l.product_name,
          quantity: l.quantity,
          modifiers: (l.modifiers ?? []).map((m) => ({ name: m.name })),
          item_note: l.item_note ?? null,
        })),
        width: 48,
      });
    } catch {
      /* printer error — cancellation KOT goes to disk via the main-process fallback */
    }
  }

  return { wasOpenOrder, hadFired };
}
