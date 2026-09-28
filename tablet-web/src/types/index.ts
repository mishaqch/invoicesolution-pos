/**
 * Shared TS types for the waiter tablet.
 *
 * Server response types are GROUNDED in the real Django serializers/views:
 *   - restaurant payloads: backend/apps/restaurant/views.py (_order_payload,
 *     _order_detail_payload, FloorView) + serializers.py
 *   - catalog: backend/apps/catalog/serializers.py (ProductPosSerializer,
 *     CategorySerializer) via GET /api/catalog/sync/
 *   - sales: backend/apps/sales/serializers.py (InvoiceSerializer)
 * Field names are copied verbatim from those payloads — do not invent keys.
 */

export type { PosProduct, Category, TaxRate, UnitOfMeasure } from "@pos/shared/types";
export type { Role, User } from "@pos/shared/types";
export type { Tenant } from "@pos/shared/types";

/* ---------------------------------------------------------------------------
 * Terminal pairing + roster (POST /api/terminals/pair/, /api/terminals/roster/)
 * ------------------------------------------------------------------------- */
export interface PairResponse {
  tenant_id: string;
  tenant_name: string;
  branch_id: string;
  branch_name: string;
  branch_code: string;
  branch_fbr_pos_id: string | null;
  terminal_id: string;
  terminal_name: string;
  terminal_index: number;
  sdc_url: string | null;
}

export interface RosterStaff {
  name: string;
  email: string;
  role: string;
  has_pin: boolean;
}

export interface RosterResponse {
  branch_id: string;
  branch_name: string;
  staff: RosterStaff[];
}

/* ---------------------------------------------------------------------------
 * PIN login (POST /api/auth/pin-login/) — mirrors the standard AuthResponse
 * ------------------------------------------------------------------------- */
export interface PinLoginResponse {
  access: string;
  refresh: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    [k: string]: unknown;
  };
  tenant: { id: string; name: string; [k: string]: unknown } | null;
  role: string | null;
}

/* ---------------------------------------------------------------------------
 * Catalog sync (GET /api/catalog/sync/) — CatalogSyncView
 * ------------------------------------------------------------------------- */
import type { PosProduct, Category } from "@pos/shared/types";

export interface ProductBatchPos {
  id: string;
  product: string;
  batch_number: string;
  expiry_date: string | null;
  current_quantity: string;
  branch: string | null;
}

export interface CatalogSyncResponse {
  products: PosProduct[];
  categories: Category[];
  batches: ProductBatchPos[];
  batches_full_snapshot: boolean;
}

/* ---------------------------------------------------------------------------
 * Restaurant order status (order_status on the order payload)
 * ------------------------------------------------------------------------- */
export type OrderStatus = "open" | "sent_to_kitchen" | "ready" | "served";

/** One modifier attached to a cart line. The wire shape is loose JSON — the
 *  server stores `modifiers` as an array; each entry carries at least a name. */
export interface LineModifier {
  name: string;
  price_delta?: string | number;
  [k: string]: unknown;
}

/* ---------------------------------------------------------------------------
 * Order payloads — restaurant/views.py
 * ------------------------------------------------------------------------- */

/** One item in the compact `items[]` array of _order_payload. */
export interface OrderPayloadItem {
  name: string;
  quantity: string;
  modifiers: LineModifier[];
  item_note: string;
  course: string | null;
  sent_to_kitchen: boolean;
  is_cancelled: boolean;
}

/** _order_payload — the compact order shape used by the floor, open-orders
 *  list, and (as `order`) each occupied table. */
export interface OrderPayload {
  id: string;
  local_invoice_number: number | string | null;
  order_type: string;
  order_status: OrderStatus;
  held_label: string | null;
  table: string | null;
  table_id: string | null;
  covers: number;
  kitchen_sent_at: string | null;
  grand_total: string;
  items: OrderPayloadItem[];
}

/** One line in the detail payload's `cart_lines[]` (full, resumable). */
export interface OrderDetailCartLine {
  product: string;
  product_name: string;
  product_sku: string;
  uom_code: string;
  hs_code: string;
  quantity: string;
  unit_price: string;
  discount_pct: string;
  discount_amount: string;
  tax_rate: string;
  modifiers: LineModifier[];
  item_note: string;
  course: string | null;
  sent_to_kitchen: boolean;
}

/** _order_detail_payload — everything in OrderPayload PLUS cart_lines +
 *  client_uuid + customer_id. Returned by POST create/upsert and GET ?id=. */
export interface OrderDetailPayload extends OrderPayload {
  cart_lines: OrderDetailCartLine[];
  client_uuid: string;
  customer_id: string | null;
}

/** GET /api/restaurant/orders/?branch=&terminal= */
export interface OpenOrdersResponse {
  orders: OrderPayload[];
}

/** DELETE /api/restaurant/orders/?client_uuid= */
export interface VoidOrderResponse {
  voided: boolean;
}

/* ---------------------------------------------------------------------------
 * Floor (GET /api/restaurant/floor/) — FloorView
 * ------------------------------------------------------------------------- */
export interface FloorTable {
  id: string;
  name: string;
  seats: number;
  zone: string | null;
  order: OrderPayload | null;
}

export interface FloorResponse {
  tables: FloorTable[];
}

/* ---------------------------------------------------------------------------
 * Tables + modifier groups (paginated) — TableSerializer, ModifierGroupSerializer
 * ------------------------------------------------------------------------- */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface TableRow {
  id: string;
  branch: string;
  branch_name: string;
  name: string;
  seats: number;
  zone: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModifierOption {
  id: string;
  group: string;
  name: string;
  price_delta: string;
  display_order: number;
  is_active: boolean;
}

export interface ModifierGroup {
  id: string;
  name: string;
  min_select: number;
  max_select: number;
  display_order: number;
  is_active: boolean;
  modifiers: ModifierOption[];
  created_at: string;
  updated_at: string;
}

/* ---------------------------------------------------------------------------
 * Completed invoices (GET /api/sales/invoices/) — InvoiceSerializer (subset)
 * ------------------------------------------------------------------------- */
export interface InvoiceItem {
  id: string;
  line_number: number;
  product: string | null;
  product_name: string;
  quantity: string;
  unit_price: string;
  line_total: string;
  is_cancelled: boolean;
}

export interface Invoice {
  id: string;
  branch: string;
  local_invoice_number: number | string | null;
  order_type: string;
  table: string | null;
  table_name: string | null;
  covers: number;
  buyer_name: string;
  held_label: string | null;
  grand_total: string;
  status: string;
  is_held: boolean;
  created_at: string;
  items: InvoiceItem[];
}

export type InvoiceListResponse = Paginated<Invoice>;

/* ---------------------------------------------------------------------------
 * Client-side order draft (order store) — NOT a server type
 * ------------------------------------------------------------------------- */
export type OrderType = "dine_in" | "takeaway" | "delivery";

/** One line of the working cart. `sent_to_kitchen` echoes back to the server
 *  on every POST so partially-fired orders keep their locked quantities. */
export interface CartLine {
  product: string;
  product_name: string;
  unit_price: number; // integer paisa-free rupees for display math (see money.ts)
  tax_rate: string | null; // = PosProduct.tax_rate_value
  quantity: number;
  discount_pct?: number;
  discount_amount?: number;
  modifiers?: LineModifier[];
  item_note?: string;
  course?: string | null;
  sent_to_kitchen: boolean;
  /** Emoji glyph for the plate (derived from name; presentation only). */
  glyph?: string;
  /** "g" vegetarian | "n" non-veg — presentation only. */
  veg?: "g" | "n";
}

export interface OrderDraft {
  clientUuid: string | null;
  localInvoiceNumber: number | string | null;
  orderType: OrderType;
  tableId: string | null;
  tableName: string | null;
  covers: number;
  heldLabel: string | null;
  status: OrderStatus;
  lines: CartLine[];
}
