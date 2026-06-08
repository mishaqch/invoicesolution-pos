/**
 * Sale store — the cart state.
 *
 * State machine:
 *   empty → has_items → payment → success → empty (auto-advance)
 *   has_items ↔ held (via held_label)
 *
 * Side effects (printer, drawer, IPC) are kicked off from the route
 * components; this store stays pure.
 */

import { create } from "zustand";

import { Money } from "@/lib/money";
import { newClientUuid } from "@/lib/uuid";

export interface CartLine {
  /** Local row id within the cart (UUIDv4). */
  id: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  uom_code: string;
  hs_code: string | null;
  quantity: string;          // 4dp string
  unit_price: string;        // 4dp string
  discount_pct: string;      // 0–100, 2dp string
  discount_amount: string;   // 4dp string (extra fixed discount)
  tax_rate: string;          // 0–100
  is_taxable: boolean;
  notes?: string;
  // FEFO (pharmacy / batch-tracked goods): the specific batch this line draws
  // from, auto-selected nearest-expiry-first when the product is added. Absent
  // for non-batch-tracked products (the common case). batch_number/expiry_date
  // are display-only; batch_id is what the checkout payload carries.
  batch_id?: string | null;
  batch_number?: string | null;
  expiry_date?: string | null;
}

export interface SelectedCustomer {
  id: string;
  name: string;
  phone: string | null;
  cnic: string | null;
  ntn: string | null;
  registration_type: "registered" | "unregistered";
  province: string | null;
}

export type SaleStage =
  | "empty"
  | "has_items"
  | "payment"
  | "success";

interface SaleState {
  clientUuid: string;
  stage: SaleStage;
  lines: CartLine[];
  customer: SelectedCustomer | null;
  cartDiscountPct: string;     // 0–100

  addLine: (line: Omit<CartLine, "id" | "quantity"> & { quantity?: string }) => void;
  updateLine: (id: string, patch: Partial<CartLine>) => void;
  removeLine: (id: string) => void;
  setQuantity: (id: string, qty: string) => void;

  setCustomer: (c: SelectedCustomer | null) => void;
  setCartDiscountPct: (pct: string) => void;

  setStage: (s: SaleStage) => void;
  resetForNewSale: () => void;
  loadFromHold: (payload: {
    clientUuid: string;
    lines: CartLine[];
    customer: SelectedCustomer | null;
    cartDiscountPct: string;
  }) => void;
}

const blank = (): Pick<SaleState, "clientUuid" | "stage" | "lines" | "customer" | "cartDiscountPct"> => ({
  clientUuid: newClientUuid(),
  stage: "empty",
  lines: [],
  customer: null,
  cartDiscountPct: "0",
});

export const useSaleStore = create<SaleState>((set, get) => ({
  ...blank(),

  addLine: (input) => {
    const newId = crypto.randomUUID();
    set((state) => {
      const existingIdx = state.lines.findIndex((l) => l.product_id === input.product_id);
      if (existingIdx >= 0) {
        // Increment quantity by 1 instead of inserting a duplicate line.
        const existing = state.lines[existingIdx];
        const next = Money.fromStr(existing.quantity).add(Money.fromStr(input.quantity ?? "1"));
        const updated = [...state.lines];
        updated[existingIdx] = { ...existing, quantity: next.toStorageString() };
        return { lines: updated, stage: "has_items" };
      }
      return {
        lines: [
          ...state.lines,
          {
            id: newId,
            quantity: input.quantity ?? "1",
            ...input,
          } as CartLine,
        ],
        stage: "has_items",
      };
    });
  },

  updateLine: (id, patch) =>
    set((state) => ({
      lines: state.lines.map((l) => (l.id === id ? { ...l, ...patch } : l)),
    })),

  removeLine: (id) =>
    set((state) => {
      const lines = state.lines.filter((l) => l.id !== id);
      return {
        lines,
        stage: lines.length === 0 ? "empty" : state.stage,
      };
    }),

  setQuantity: (id, qty) => get().updateLine(id, { quantity: qty }),

  setCustomer: (c) => set({ customer: c }),
  setCartDiscountPct: (pct) => set({ cartDiscountPct: pct }),

  setStage: (s) => set({ stage: s }),

  resetForNewSale: () => set({ ...blank() }),

  loadFromHold: (payload) =>
    set({
      clientUuid: payload.clientUuid,
      lines: payload.lines,
      customer: payload.customer,
      cartDiscountPct: payload.cartDiscountPct,
      stage: payload.lines.length > 0 ? "has_items" : "empty",
    }),
}));

// ---------------------------------------------------------------------------
// Selectors — pricing math via Money.
// ---------------------------------------------------------------------------

export interface QuotedLine extends CartLine {
  gross: Money;
  line_discount: Money;
  net: Money;
  tax_amount: Money;
  line_total: Money;
}

export interface CartTotals {
  lines: QuotedLine[];
  subtotal: Money;
  line_discount_total: Money;
  cart_discount_amount: Money;
  discount_total: Money;
  tax_total: Money;
  grand_total: Money;
}

export function quoteCart(state: Pick<SaleState, "lines" | "cartDiscountPct">): CartTotals {
  const quoted: QuotedLine[] = state.lines.map((l) => {
    const gross = Money.fromStr(l.unit_price).mulScalar(l.quantity);
    const pctDisc = gross.applyPct(l.discount_pct || "0");
    const fixedDisc = Money.fromStr(l.discount_amount || "0");
    let lineDiscount = pctDisc.add(fixedDisc);
    let net = gross.sub(lineDiscount);
    if (net.isNegative()) {
      net = Money.zero();
      lineDiscount = gross;
    }
    const tax = l.is_taxable ? net.applyPct(l.tax_rate || "0") : Money.zero();
    const lineTotal = net.add(tax);
    return { ...l, gross, line_discount: lineDiscount, net, tax_amount: tax, line_total: lineTotal };
  });

  const subtotal = quoted.reduce((acc, q) => acc.add(q.gross), Money.zero());
  const lineDiscountTotal = quoted.reduce((acc, q) => acc.add(q.line_discount), Money.zero());
  const preCartNet = quoted.reduce((acc, q) => acc.add(q.net), Money.zero());
  const taxTotal = quoted.reduce((acc, q) => acc.add(q.tax_amount), Money.zero());

  let cartDiscount = preCartNet.applyPct(state.cartDiscountPct || "0");
  if (cartDiscount.gt(preCartNet)) cartDiscount = preCartNet;

  const grandTotal = preCartNet.add(taxTotal).sub(cartDiscount);

  return {
    lines: quoted,
    subtotal,
    line_discount_total: lineDiscountTotal,
    cart_discount_amount: cartDiscount,
    discount_total: lineDiscountTotal.add(cartDiscount),
    tax_total: taxTotal,
    grand_total: grandTotal,
  };
}
