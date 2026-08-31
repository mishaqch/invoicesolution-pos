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
  items: { name: string; quantity: string }[];
}

export interface OpenOrderDetail extends OpenOrderSummary {
  client_uuid: string;
  customer_id: string | null;
  cart_lines: {
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

/** Create/update the server-side open order (fire kitchen). Idempotent on client_uuid. */
export function fireOpenOrder(payload: FireOrderPayload): Promise<OpenOrderDetail> {
  return api<OpenOrderDetail>("/restaurant/orders/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** List the open orders (the table/order book) for resuming. Terminal-scoped:
 * each till gets ONLY its own open orders, so one terminal never sees another
 * terminal's unpaid orders. (Admin/KDS views can still list a whole branch.) */
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
