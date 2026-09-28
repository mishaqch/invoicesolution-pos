import { api } from "@/lib/api";
import type {
  FloorResponse,
  ModifierGroup,
  OpenOrdersResponse,
  OrderDetailPayload,
  Paginated,
  TableRow,
  VoidOrderResponse,
} from "@/types";

/** GET /api/restaurant/floor/?branch=<id> — tables with occupancy. */
export function getFloor(branchId: string): Promise<FloorResponse> {
  return api<FloorResponse>(`/restaurant/floor/?branch=${encodeURIComponent(branchId)}`);
}

/** GET /api/restaurant/tables/?branch=<id> — PAGINATED; caller gets rows. */
export async function getTables(branchId: string): Promise<TableRow[]> {
  const page = await api<Paginated<TableRow>>(
    `/restaurant/tables/?branch=${encodeURIComponent(branchId)}`,
  );
  return page.results;
}

/** GET /api/restaurant/modifier-groups/?product=<id> — PAGINATED. */
export async function getModifierGroups(productId: string): Promise<ModifierGroup[]> {
  const page = await api<Paginated<ModifierGroup>>(
    `/restaurant/modifier-groups/?product=${encodeURIComponent(productId)}`,
  );
  return page.results;
}

/** GET /api/restaurant/orders/?branch=<id>&terminal=<id> — open/held list. */
export function getOpenOrders(branchId: string, terminalId: string): Promise<OpenOrdersResponse> {
  return api<OpenOrdersResponse>(
    `/restaurant/orders/?branch=${encodeURIComponent(branchId)}&terminal=${encodeURIComponent(terminalId)}`,
  );
}

/** GET /api/restaurant/orders/?id=<invoiceId>&terminal=<terminalId> — detail. */
export function getOpenOrder(invoiceId: string, terminalId: string): Promise<OrderDetailPayload> {
  return api<OrderDetailPayload>(
    `/restaurant/orders/?id=${encodeURIComponent(invoiceId)}&terminal=${encodeURIComponent(terminalId)}`,
  );
}

export interface UpsertOrderBody {
  client_uuid: string;
  branch: string;
  terminal: string;
  order_type: string;
  table?: string | null;
  covers?: number;
  held_label?: string | null;
  cart_lines: Array<{
    product: string;
    quantity: number;
    unit_price?: number | string;
    // tax_rate + is_taxable are needed by the server's quote_cart to compute the
    // held order's tax_total (shown on Floor/KDS). Omitting them makes the server
    // quote tax as 0. The POS terminal sends both on its fire; the tablet mirrors
    // it so a fiscal restaurant's held-order totals aren't understated.
    tax_rate?: number | string | null;
    is_taxable?: boolean;
    modifiers?: Array<Record<string, unknown>>;
    item_note?: string;
    course?: string | null;
    sent_to_kitchen?: boolean;
  }>;
  /** true = Send to kitchen; false = Save (park). */
  fire: boolean;
}

/** POST /api/restaurant/orders/ — idempotent on client_uuid. */
export function upsertOrder(body: UpsertOrderBody): Promise<OrderDetailPayload> {
  return api<OrderDetailPayload>("/restaurant/orders/", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** DELETE /api/restaurant/orders/?client_uuid=<uuid> -> {voided}. */
export function voidOrder(clientUuid: string): Promise<VoidOrderResponse> {
  return api<VoidOrderResponse>(
    `/restaurant/orders/?client_uuid=${encodeURIComponent(clientUuid)}`,
    { method: "DELETE" },
  );
}
