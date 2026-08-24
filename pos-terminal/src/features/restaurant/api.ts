/** Restaurant terminal API calls (online — kitchen + open orders live on the
 *  server so Floor/KDS see them during service). */

import { api } from "@/lib/api";

export interface OpenOrderSummary {
  id: string;
  local_invoice_number: string;
  order_type: string | null;
  order_status: string | null;
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

/** List the open orders (the table/order book) for resuming. */
export function listOpenOrders(branchId?: string | null): Promise<{ orders: OpenOrderSummary[] }> {
  return api(`/restaurant/orders/${branchId ? `?branch=${branchId}` : ""}`);
}

/** One open order with cart_lines to rebuild the cart on resume. */
export function getOpenOrder(id: string): Promise<OpenOrderDetail> {
  return api(`/restaurant/orders/?id=${id}`);
}
