/** Restaurant terminal API calls (online — kitchen + open orders live on the
 *  server so Floor/KDS see them during service). */

import { api } from "@/lib/api";

export interface OpenOrderSummary {
  id: string;
  local_invoice_number: string;
  order_type: string | null;
  order_status: string | null;
  // Cashier's reference set via "Save order" (e.g. "Table 3 / Ahmed").
  held_label: string | null;
  table: string | null;
  table_id: string | null;
  covers: number | null;
  grand_total: string;
  // True when this order was fired from a shared waiter tablet (not this or
  // another cashier till) — the UI badges it so the cashier can tell a
  // floor-fired order apart from their own parked ticket.
  from_waiter_tablet?: boolean;
  items: { name: string; quantity: string }[];
}

export interface OpenOrderDetail extends OpenOrderSummary {
  client_uuid: string;
  customer_id: string | null;
  cart_lines: {
    /** SaleItem id — needed to ack a KOT print via markKotPrinted(). */
    id?: string;
    /** True once some terminal has printed this line's KOT. */
    kot_printed?: boolean;
    product: string;
    product_name: string;
    product_sku: string;
    uom_code: string;
    hs_code: string | null;
    quantity: string;
    unit_price: string;
    discount_pct: string;
    discount_amount: string;
    tax_rate: string;
    modifiers: { name: string; price: string }[];
    item_note: string | null;
    course: number | null;
    sent_to_kitchen: boolean;
  }[];
}

export interface FireOrderPayload {
  client_uuid: string;
  terminal: string;
  branch: string;
  order_type: string | null;
  table: string | null;
  covers: number | null;
  buyer_name?: string | null;
  buyer_phone?: string | null;
  cart_discount_pct?: string;
  // The order's local invoice number (KK-T3-…). Sent so the server open order —
  // and later the finalized invoice — carry the SAME number the KOT shows.
  local_invoice_number?: string | null;
  // Cashier's free-text reference for an order parked via "Save order" (e.g.
  // "Table 3 / Ahmed"). Shown in the Open-orders list so they can find it.
  held_label?: string | null;
  // true = "Send to kitchen" (fire: KDS + KOT). false = "Save order" (park in
  // Open orders without alerting the kitchen). Omitted = true (server default).
  fire?: boolean;
  cart_lines: {
    product: string;
    quantity: string;
    unit_price: string;
    discount_pct: string;
    discount_amount: string;
    tax_rate: string;
    is_taxable: boolean;
    modifiers: { name: string; price: string }[];
    item_note: string | null;
    course: number | null;
    // Per-line fired flag — preserved across save/re-fire so a "Save order"
    // never un-fires a line that already went to the kitchen.
    sent_to_kitchen?: boolean;
  }[];
}

/**
 * Ack a KOT print: stamp kot_printed_at on exactly these lines.
 *
 * The firing till must call this after printing its own slip. The server's
 * unprinted feed is (sent_to_kitchen AND kot_printed_at IS NULL), so a line
 * left unacked is re-served to the KOT relay and printed a second time.
 * Server-side the UPDATE is conditional on IS NULL, so retries are safe.
 */
export function markKotPrinted(
  invoiceId: string,
  itemIds: string[],
  terminalId?: string | null,
): Promise<{ marked: number }> {
  return api(`/restaurant/orders/${invoiceId}/mark-printed/`, {
    method: "POST",
    body: JSON.stringify({
      item_ids: itemIds,
      ...(terminalId ? { terminal_id: terminalId } : {}),
    }),
  });
}

/**
 * POST the PAID invoice straight to the server from the renderer.
 *
 * The charge path used to rely solely on the background sync worker. That is
 * fragile: the worker runs in a utility process with its OWN copy of the auth
 * token, and if it has none it silently skips every row — which is exactly how
 * paid orders ended up stranded on the Open orders screen while the cashier
 * saw no error at all.
 *
 * This renderer path uses the live in-memory token — the same one that fires
 * orders to the kitchen all day — so the sale reaches the server immediately
 * and the open order clears at once. The worker queue stays as the offline
 * fallback; the server is idempotent on client_uuid, so both arriving is a
 * no-op ("duplicate").
 */
export function syncInvoiceNow(payload: unknown): Promise<{ sync_status?: string }> {
  return api("/sync/invoices/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Create/update the server-side open order (fire kitchen). Idempotent on client_uuid. */
export function fireOpenOrder(payload: FireOrderPayload): Promise<OpenOrderDetail> {
  return api<OpenOrderDetail>("/restaurant/orders/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** List the open orders (the table/order book) for resuming. Terminal-scoped:
 * a till sees its OWN open orders PLUS every order fired from a shared "waiter
 * tablet" (is_order_taking_only) terminal — those have no till of their own and
 * must be chargeable on any cashier till in the branch (the handoff). Ordinary
 * tills still never see each other's parked orders. (Admin/KDS omit `terminal`
 * to list the whole branch.) */
export function listOpenOrders(
  branchId?: string | null,
  terminalId?: string | null,
): Promise<{ orders: OpenOrderSummary[] }> {
  const params = new URLSearchParams();
  if (branchId) params.set("branch", branchId);
  if (terminalId) params.set("terminal", terminalId);
  const qs = params.toString();
  return api(`/restaurant/orders/${qs ? `?${qs}` : ""}`);
}

/** One open order with cart_lines to rebuild the cart on resume. Passing the
 * terminal id lets the server refuse to resume another terminal's order (a
 * table shows "occupied but not openable" on other tills). */
export function getOpenOrder(id: string, terminalId?: string | null): Promise<OpenOrderDetail> {
  const params = new URLSearchParams({ id });
  if (terminalId) params.set("terminal", terminalId);
  return api(`/restaurant/orders/?${params.toString()}`);
}

/**
 * Void (soft-delete) an open order so it leaves the book. Called when a resumed
 * open order has all its items removed — an empty order is a voided order.
 * Keyed on the same client_uuid the order was saved with. Idempotent server-side.
 */
export function voidOpenOrder(clientUuid: string): Promise<{ voided: boolean }> {
  return api(`/restaurant/orders/?client_uuid=${encodeURIComponent(clientUuid)}`, {
    method: "DELETE",
  });
}
