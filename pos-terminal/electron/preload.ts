/**
 * Preload — exposes a typed `window.api` to the renderer via contextBridge.
 * The renderer never sees `node:` modules or better-sqlite3 directly.
 */

import { contextBridge, ipcRenderer } from "electron";

export interface PosProductSqliteRow {
  id: string;
  category_id: string | null;
  sku: string;
  barcode: string | null;
  name: string;
  name_ur: string | null;
  uom_code: string;
  tax_rate_id: string | null;
  is_taxable: number;
  sale_price: string;
  retail_price: string | null;
  min_sale_price: string | null;
  max_discount_pct: string | null;
  is_weighable: number;
  image_url: string | null;
  is_active: number;
  updated_at: string;
  deleted_at: string | null;
}

export interface PosCashSessionRow {
  id: string;
  branch_id: string;
  terminal_id: string;
  cashier_id: string;
  opened_at: string;
  opened_with_amount: string;
  closed_at: string | null;
  closed_with_amount: string | null;
  expected_amount: string | null;
  variance: string | null;
  variance_reason: string | null;
  total_sales: string;
  cash_in: string;
  cash_out: string;
  status: "open" | "closed";
}

export interface PosInvoiceRow {
  id: string;
  client_uuid: string;
  local_invoice_number: string;
  status: string;
  invoice_date: string;
  customer_id: string | null;
  buyer_name: string | null;
  buyer_phone: string | null;
  buyer_ntn_cnic: string | null;
  buyer_registration_type: string | null;
  branch_id: string;
  terminal_id: string;
  cashier_id: string;
  cash_session_id: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  change_given: string;
  is_held: number;
  held_label: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PosSaleItemRow {
  id: string;
  invoice_id: string;
  line_number: number;
  product_id: string;
  product_name: string;
  product_sku: string;
  uom_code: string;
  hs_code: string | null;
  quantity: string;
  unit_price: string;
  discount_pct: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  line_total: string;
  notes: string | null;
}

export interface PosPaymentRow {
  id: string;
  invoice_id: string;
  payment_method: string;
  amount: string;
  status: string;
  created_at: string;
}

const api = {
  meta: {
    get: (key: string): Promise<string | null> => ipcRenderer.invoke("meta:get", key),
    set: (key: string, value: string): Promise<void> => ipcRenderer.invoke("meta:set", key, value),
  },
  queue: {
    enqueue: (entry: {
      client_uuid: string;
      entity_type: string;
      entity_id: string;
      action: string;
      payload: unknown;
    }): Promise<number> => ipcRenderer.invoke("queue:enqueue", entry),
    pendingCount: (): Promise<number> => ipcRenderer.invoke("queue:pending-count"),
  },
  catalog: {
    sync: (opts: { apiBase: string; accessToken: string }): Promise<{
      products: number;
      categories: number;
    }> => ipcRenderer.invoke("catalog:sync", opts),
    search: (query: string, limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:search", query, limit),
    list: (limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:list", limit),
    count: (): Promise<number> => ipcRenderer.invoke("catalog:count"),
  },
  sales: {
    persistInvoice: (args: unknown): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:persist-invoice", args),
    list: (opts: { held?: boolean; limit?: number } = {}): Promise<PosInvoiceRow[]> =>
      ipcRenderer.invoke("sales:list", opts),
    get: (invoice_id: string): Promise<{
      invoice: PosInvoiceRow;
      items: PosSaleItemRow[];
      payments: PosPaymentRow[];
    } | null> => ipcRenderer.invoke("sales:get", invoice_id),
    hold: (invoice_id: string, label: string): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:hold", invoice_id, label),
    recall: (invoice_id: string): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:recall", invoice_id),
  },
  session: {
    open: (payload: PosCashSessionRow): Promise<{ ok: true }> =>
      ipcRenderer.invoke("session:open", payload),
    current: (terminal_id: string): Promise<PosCashSessionRow | null> =>
      ipcRenderer.invoke("session:current", terminal_id),
    totals: (session_id: string): Promise<{ total_sales: string }> =>
      ipcRenderer.invoke("session:totals", session_id),
    close: (
      id: string,
      args: {
        closed_at: string;
        closed_with_amount: string;
        expected_amount: string;
        variance: string;
        variance_reason: string;
      },
    ): Promise<{ ok: true }> => ipcRenderer.invoke("session:close", id, args),
  },
  printer: {
    print: (payload: unknown): Promise<{ success: boolean; reason?: string; fallbackPath?: string }> =>
      ipcRenderer.invoke("printer:print-receipt", payload),
  },
  drawer: {
    open: (): Promise<{ success: boolean; reason?: string }> =>
      ipcRenderer.invoke("drawer:open"),
  },
  customerDisplay: {
    /**
     * Send a message to the customer-facing display (second monitor).
     * Returns { success: false } when no secondary display is attached
     * — the cashier flow continues regardless. Payload shapes match
     * what customer-display/src/App.tsx expects:
     *   { type: "idle" }
     *   { type: "sale", lines, total, business }
     *   { type: "qr", url, amount }
     *   { type: "thanks" }
     */
    post: (payload: unknown): Promise<{ success: boolean }> =>
      ipcRenderer.invoke("customerDisplay:post", payload),
  },
  sync: {
    setTokens: (access: string | null, refresh: string | null): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sync:set-tokens", access, refresh),
    kick: (): Promise<{ ok: true }> => ipcRenderer.invoke("sync:kick"),
    status: (): Promise<{
      counts: { pending: number; ok: number; failed: number };
      last_processed_at: string | null;
      last_error: string | null;
    }> => ipcRenderer.invoke("sync:status"),
    retryFailed: (): Promise<{ retried: number }> =>
      ipcRenderer.invoke("sync:retry-failed"),
    onStatus: (cb: (s: {
      counts: { pending: number; ok: number; failed: number };
      last_processed_at: string | null;
      last_error: string | null;
    }) => void) => {
      const handler = (_e: unknown, s: unknown) => cb(s as Parameters<typeof cb>[0]);
      ipcRenderer.on("sync:status-changed", handler);
      return () => ipcRenderer.off("sync:status-changed", handler);
    },
  },
  numbering: {
    next: (args: { branchCode: string; terminalIndex: number }): Promise<string> =>
      ipcRenderer.invoke("numbering:next", args),
  },
};

contextBridge.exposeInMainWorld("api", api);

export type PosApi = typeof api;
