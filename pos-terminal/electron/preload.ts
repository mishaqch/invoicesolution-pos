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
  /** Numeric tax % resolved from the product's tax_rate FK (e.g. "16.00"). */
  tax_rate_value: string | null;
  hs_code: string | null;
  is_taxable: number;
  sale_price: string;
  retail_price: string | null;
  min_sale_price: string | null;
  max_discount_pct: string | null;
  is_third_schedule: number;
  is_weighable: number;
  is_batch_tracked: number;
  image_url: string | null;
  is_active: number;
  updated_at: string;
  deleted_at: string | null;
}

export interface PosBatchSqliteRow {
  id: string;
  product_id: string;
  batch_number: string;
  expiry_date: string | null;
  current_quantity: string;
  branch_id: string | null;
}

export interface PosCategoryRow {
  id: string;
  name: string;
  display_order: number;
  color: string | null;
  icon: string | null;
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
  // FBR submission state — populated by the sync worker after the
  // backend echoes back the PRAL response (Phase 4). Nullable because
  // unsynced / pending invoices haven't been to PRAL yet.
  fbr_invoice_number: string | null;
  fbr_qr_payload: string | null;
  fbr_submitted_at: string | null;
  fbr_validated_at: string | null;
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

export interface PosPairedIdentity {
  terminalId: string;
  terminalName: string;
  terminalIndex: number;
  branchId: string;
  branchName: string;
  branchCode: string;
  branchFbrPosId: string | null;
  tenantId: string;
  tenantName: string;
  sdcUrl: string;
}

const api = {
  meta: {
    get: (key: string): Promise<string | null> => ipcRenderer.invoke("meta:get", key),
    set: (key: string, value: string): Promise<void> => ipcRenderer.invoke("meta:set", key, value),
  },
  pairing: {
    status: (): Promise<{ paired: boolean; identity: PosPairedIdentity | null }> =>
      ipcRenderer.invoke("pairing:status"),
    pair: (code: string): Promise<{ ok: boolean; identity?: PosPairedIdentity; error?: string }> =>
      ipcRenderer.invoke("pairing:pair", code),
    unpair: (): Promise<{ ok: true }> => ipcRenderer.invoke("pairing:unpair"),
  },
  sdc: {
    getUrl: (): Promise<string> => ipcRenderer.invoke("sdc:get-url"),
    setUrl: (url: string): Promise<{ ok: true }> => ipcRenderer.invoke("sdc:set-url", url),
    health: (): Promise<{ ok: boolean; message: string }> => ipcRenderer.invoke("sdc:health"),
  },
  fiscalize: {
    invoice: (invoiceId: string): Promise<{
      ok: boolean;
      fbrInvoiceNumber?: string;
      alreadyFiscalized?: boolean;
      reason?: string;
    }> => ipcRenderer.invoke("fiscalize:invoice", invoiceId),
    // FBR test mode (no SDC): is it on, toggle it, and stamp a dummy number.
    isTestMode: (): Promise<boolean> => ipcRenderer.invoke("fiscalize:test-mode-on"),
    setTestMode: (on: boolean): Promise<{ ok: true }> =>
      ipcRenderer.invoke("fiscalize:set-test-mode", on),
    testStamp: (args: { invoiceId: string; localNumber: string }): Promise<{
      ok: boolean; fbrInvoiceNumber?: string;
    }> => ipcRenderer.invoke("fiscalize:test-stamp", args),
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
    sync: (opts: { apiBase: string; accessToken: string; tenantId?: string | null; force?: boolean }): Promise<{
      products: number;
      categories: number;
      batches: number;
    }> => ipcRenderer.invoke("catalog:sync", opts),
    search: (query: string, limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:search", query, limit),
    list: (limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:list", limit),
    // Category quick-filter on the till (Rooms pinned first for the resort).
    categories: (): Promise<PosCategoryRow[]> => ipcRenderer.invoke("catalog:categories"),
    byCategory: (categoryId: string, limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:by-category", categoryId, limit),
    byBarcode: (barcode: string): Promise<PosProductSqliteRow | null> =>
      ipcRenderer.invoke("catalog:by-barcode", barcode),
    count: (): Promise<number> => ipcRenderer.invoke("catalog:count"),
    // FEFO: nearest-expiry in-stock batch for a batch-tracked product.
    nearestBatch: (productId: string, branchId?: string | null): Promise<PosBatchSqliteRow | null> =>
      ipcRenderer.invoke("catalog:nearest-batch", productId, branchId),
    batches: (productId: string, branchId?: string | null): Promise<PosBatchSqliteRow[]> =>
      ipcRenderer.invoke("catalog:batches", productId, branchId),
  },
  sales: {
    persistInvoice: (args: unknown): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:persist-invoice", args),
    /** Mirror a server-created invoice (e.g. hotel folio charge) into local
     *  SQLite for display — no sync enqueue (server already owns it). */
    persistServerInvoice: (args: unknown): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:persist-server-invoice", args),
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
    deleteHeld: (invoice_id: string): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:delete-held", invoice_id),
    setFbrFields: (args: {
      invoice_id: string;
      fbr_invoice_number: string;
      fbr_qr_payload: string | null;
      fbr_validated_at: string | null;
    }): Promise<{ ok: true }> =>
      ipcRenderer.invoke("sales:set-fbr-fields", args),
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
    printKOT: (payload: unknown): Promise<{ success: boolean; reason?: string; fallbackPath?: string }> =>
      ipcRenderer.invoke("printer:print-kot", payload),
    printFolio: (payload: unknown): Promise<{ success: boolean; reason?: string; fallbackPath?: string }> =>
      ipcRenderer.invoke("printer:print-folio", payload),
    /** Print a diagnostic slip. Pass an interface string to test before saving. */
    test: (iface?: string): Promise<{ success: boolean; reason?: string; fallbackPath?: string }> =>
      ipcRenderer.invoke("printer:test", iface),
    /** List installed Windows printers (name + default) for the picker. */
    listWindows: (): Promise<{ name: string; isDefault: boolean }[]> =>
      ipcRenderer.invoke("printer:list-windows"),
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
    // Reconnect: reset pending backoff + retry now (online/resume transitions).
    expedite: (): Promise<{ ok: true }> => ipcRenderer.invoke("sync:expedite"),
    status: (): Promise<{
      counts: { pending: number; ok: number; failed: number };
      last_processed_at: string | null;
      last_error: string | null;
    }> => ipcRenderer.invoke("sync:status"),
    retryFailed: (): Promise<{ retried: number }> =>
      ipcRenderer.invoke("sync:retry-failed"),
    listPending: (limit?: number): Promise<Array<{
      id: number;
      client_uuid: string;
      entity_type: string;
      status: string;
      attempt_count: number;
      last_error: string | null;
      next_attempt_at: string | null;
      created_at: string;
      local_invoice_number: string | null;
      grand_total: string | null;
      invoice_date: string | null;
      fbr_invoice_number: string | null;
    }>> => ipcRenderer.invoke("sync:list-pending", limit),
    retryRow: (id: number): Promise<{ retried: number }> =>
      ipcRenderer.invoke("sync:retry-row", id),
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
  updates: {
    /** Is an update already downloaded & staged? (version or null). */
    pending: (): Promise<{ version: string | null }> =>
      ipcRenderer.invoke("update:pending"),
    /** Current app version + last updater status (for the version footer). */
    info: (): Promise<{ currentVersion: string; status: string; pendingVersion: string | null }> =>
      ipcRenderer.invoke("update:info"),
    /** Trigger an update check immediately (testing — no need to wait an hour). */
    checkNow: (): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke("update:check-now"),
    /** Restart the app now to apply the staged update. */
    installNow: (): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke("update:install-now"),
    /** Fires when an update finished downloading and is ready to install. */
    onReady: (cb: (info: { version: string }) => void) => {
      const handler = (_e: unknown, info: unknown) => cb(info as { version: string });
      ipcRenderer.on("update:ready", handler);
      return () => ipcRenderer.off("update:ready", handler);
    },
  },
};

contextBridge.exposeInMainWorld("api", api);

export type PosApi = typeof api;
