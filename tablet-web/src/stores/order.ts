import { create } from "zustand";

import { uuid } from "@/lib/uuid";
import { toRupees } from "@/lib/money";
import { glyphFor, vegFor } from "@/lib/menu-glyph";
import type {
  CartLine,
  OrderDetailPayload,
  OrderDraft,
  OrderStatus,
  OrderType,
  PosProduct,
} from "@/types";

interface OrderState extends OrderDraft {
  /** Start a brand-new order: mint ONE client_uuid, clear everything. */
  startNewOrder: () => void;
  /** Add one of a product (mints the order lazily if none is active). */
  addLine: (product: PosProduct) => void;
  /** +1 to an existing line. */
  incLine: (productId: string) => void;
  /** -1 — never below the sent_to_kitchen-locked count; removes at 0. Returns
   *  false when the decrement was blocked by the kitchen floor. */
  decLine: (productId: string) => boolean;
  setLineModifiers: (productId: string, modifiers: CartLine["modifiers"]) => void;
  setTable: (tableId: string | null, tableName: string | null, covers?: number) => void;
  setOrderType: (t: OrderType) => void;
  setHeldLabel: (label: string) => void;
  setStatus: (s: OrderStatus) => void;
  /** Mark every current line as sent (after a successful fire). */
  markAllSent: () => void;
  /** Load a server order detail back into the working draft (Resume). */
  rehydrateFromServer: (detail: OrderDetailPayload) => void;
  reset: () => void;
}

const EMPTY: OrderDraft = {
  clientUuid: null,
  localInvoiceNumber: null,
  orderType: "dine_in",
  tableId: null,
  tableName: null,
  covers: 1,
  heldLabel: null,
  status: "open",
  lines: [],
};

/** Map the server's order_type string onto our narrow OrderType union. */
function normOrderType(s: string | null | undefined): OrderType {
  if (s === "takeaway" || s === "delivery") return s;
  return "dine_in";
}

export const useOrderStore = create<OrderState>((set, get) => ({
  ...EMPTY,

  startNewOrder: () => set({ ...EMPTY, clientUuid: uuid() }),

  addLine: (product) => {
    const state = get();
    // Lazily mint an order the first time a waiter taps a dish.
    const clientUuid = state.clientUuid ?? uuid();
    const lines = [...state.lines];
    // Add to the UNSENT line for this product if one exists; a sent line stays
    // locked, so a fresh addition to an already-sent dish becomes its own new
    // unsent line (mirrors the backend's per-line sent_to_kitchen boolean and
    // the artifact's "New / Already in kitchen" split).
    const idx = lines.findIndex((l) => l.product === product.id && !l.sent_to_kitchen);
    if (idx >= 0) {
      lines[idx] = { ...lines[idx], quantity: lines[idx].quantity + 1 };
    } else {
      lines.push({
        product: product.id,
        product_name: product.name,
        unit_price: toRupees(product.sale_price),
        tax_rate: product.tax_rate_value,
        quantity: 1,
        sent_to_kitchen: false,
        glyph: glyphFor(product.name),
        veg: vegFor(product.name),
      });
    }
    set({ clientUuid, lines });
  },

  incLine: (productId) => {
    // Bump the unsent line for this product (create nothing — inc is only ever
    // called from an existing unsent line's stepper).
    const lines = get().lines.map((l) =>
      l.product === productId && !l.sent_to_kitchen ? { ...l, quantity: l.quantity + 1 } : l,
    );
    set({ lines });
  },

  decLine: (productId) => {
    const state = get();
    // Only the unsent line is editable; sent lines are locked.
    const line = state.lines.find((l) => l.product === productId && !l.sent_to_kitchen);
    if (!line) return false;
    const nq = line.quantity - 1;
    const lines =
      nq <= 0
        ? state.lines.filter((l) => !(l.product === productId && !l.sent_to_kitchen))
        : state.lines.map((l) =>
            l.product === productId && !l.sent_to_kitchen ? { ...l, quantity: nq } : l,
          );
    set({ lines });
    return true;
  },

  setLineModifiers: (productId, modifiers) => {
    const lines = get().lines.map((l) =>
      l.product === productId && !l.sent_to_kitchen ? { ...l, modifiers } : l,
    );
    set({ lines });
  },

  setTable: (tableId, tableName, covers) =>
    set((s) => ({ tableId, tableName, covers: covers ?? s.covers })),

  setOrderType: (orderType) => set({ orderType }),

  setHeldLabel: (heldLabel) => set({ heldLabel: heldLabel.trim() || null }),

  setStatus: (status) => set({ status }),

  markAllSent: () =>
    set((s) => ({ lines: s.lines.map((l) => ({ ...l, sent_to_kitchen: true })) })),

  rehydrateFromServer: (detail) => {
    const lines: CartLine[] = detail.cart_lines.map((cl) => ({
      product: cl.product,
      product_name: cl.product_name,
      unit_price: toRupees(cl.unit_price),
      tax_rate: cl.tax_rate ?? null,
      quantity: Math.round(toRupees(cl.quantity)),
      discount_pct: cl.discount_pct ? toRupees(cl.discount_pct) : undefined,
      discount_amount: cl.discount_amount ? toRupees(cl.discount_amount) : undefined,
      modifiers: cl.modifiers,
      item_note: cl.item_note || undefined,
      course: cl.course ?? null,
      sent_to_kitchen: cl.sent_to_kitchen,
      glyph: glyphFor(cl.product_name),
      veg: vegFor(cl.product_name),
    }));
    set({
      // On Resume take the client_uuid FROM the server (idempotency continuity).
      clientUuid: detail.client_uuid,
      localInvoiceNumber: detail.local_invoice_number,
      orderType: normOrderType(detail.order_type),
      tableId: detail.table_id,
      tableName: detail.table,
      covers: detail.covers || 1,
      heldLabel: detail.held_label,
      status: detail.order_status,
      lines,
    });
  },

  reset: () => set({ ...EMPTY }),
}));
