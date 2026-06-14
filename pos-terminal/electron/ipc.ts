/**
 * IPC handlers — Electron main → renderer bridge.
 *
 * Phase 0: meta + queue.
 * Phase 1: catalog sync + search.
 * Phase 2: sales (persist invoice / hold / recall / list / detail),
 *          cash sessions (open/close/totals),
 *          printer (printReceipt) + drawer (open).
 * Phase 3: sync worker bridge (status subscription, kick, manual retry,
 *          token push to worker), and the kv_meta-based local invoice
 *          numbering.
 */

import { app, ipcMain, type IpcMainInvokeEvent, BrowserWindow } from "electron";

import { getDb, getMeta, setMeta } from "./db/client";
import { nextInvoiceNumber } from "./db/numbering";
import {
  checkSdcHealth, fiscalizeInvoice, fiscalizeTestMode,
  isFbrTestMode, setFbrTestMode,
} from "./fiscalize";
import {
  getPairedIdentity, getSdcUrl, isPaired, pairWithCode, setSdcUrl, unpair,
} from "./pairing";
import {
  currentStatus, expediteWorker, kickWorker, manualRetryFailed,
  retryQueueRowById, setAuthTokens, subscribe,
} from "./sync/manager";
import {
  closeCashSession,
  deleteHeldInvoice,
  getInvoiceWithLines,
  getOpenSession,
  holdInvoice,
  listInvoices,
  listPendingSync,
  openCashSession,
  persistInvoice,
  recallInvoice,
  setInvoiceFbrFields,
  totalsForSession,
  type PosCashSession,
  type PosInvoiceInput,
  type PosPaymentInput,
  type PosSaleItemInput,
} from "./db/sales";
import {
  batchesForProduct,
  listProducts,
  nearestExpiryBatch,
  productByBarcode,
  productsCount,
  searchProducts,
  syncCatalog,
} from "./db/sync";
import { openCashDrawer, printKOT, printReceipt } from "./printer";
import { postToCustomerDisplay } from "./customer-display";

export function registerIpcHandlers(opts: { apiBase: string }) {
  const { apiBase } = opts;

  // Meta
  ipcMain.handle("meta:get", (_e, key: string) => getMeta(key));
  ipcMain.handle("meta:set", (_e, key: string, value: string) => setMeta(key, value));

  // --- Device pairing -----------------------------------------------------
  ipcMain.handle("pairing:status", () => ({
    paired: isPaired(),
    identity: getPairedIdentity(),
  }));
  ipcMain.handle("pairing:pair", async (_e, code: string) => {
    try {
      const identity = await pairWithCode(apiBase, code, app.getVersion());
      return { ok: true, identity };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : "Pairing failed." };
    }
  });
  ipcMain.handle("pairing:unpair", () => {
    unpair();
    return { ok: true };
  });

  // --- SDC config + fiscalization ----------------------------------------
  ipcMain.handle("sdc:get-url", () => getSdcUrl());
  ipcMain.handle("sdc:set-url", (_e, url: string) => {
    setSdcUrl(url);
    return { ok: true };
  });
  ipcMain.handle("sdc:health", async () => checkSdcHealth());
  ipcMain.handle("fiscalize:invoice", async (_e, invoiceId: string) =>
    fiscalizeInvoice(apiBase, invoiceId),
  );
  // FBR TEST MODE (no SDC, e.g. macOS dev): stamp a dummy FBR number locally so
  // the sale → print flow (logo + QR) is testable end-to-end.
  ipcMain.handle("fiscalize:test-mode-on", () => isFbrTestMode());
  ipcMain.handle("fiscalize:set-test-mode", (_e, on: boolean) => {
    setFbrTestMode(on);
    return { ok: true };
  });
  ipcMain.handle(
    "fiscalize:test-stamp",
    (_e, args: { invoiceId: string; localNumber: string }) =>
      fiscalizeTestMode(args.invoiceId, args.localNumber),
  );

  // Queue
  ipcMain.handle(
    "queue:enqueue",
    (
      _e,
      entry: {
        client_uuid: string;
        entity_type: string;
        entity_id: string;
        action: string;
        payload: unknown;
      },
    ) => {
      const result = getDb()
        .prepare(
          `INSERT INTO outbound_queue
             (client_uuid, entity_type, entity_id, action, payload, next_attempt_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(client_uuid) DO NOTHING`,
        )
        .run(
          entry.client_uuid, entry.entity_type, entry.entity_id, entry.action,
          JSON.stringify(entry.payload),
        );
      return result.lastInsertRowid as number;
    },
  );
  ipcMain.handle("queue:pending-count", () => {
    const row = getDb()
      .prepare("SELECT COUNT(*) AS n FROM outbound_queue WHERE status = 'pending'")
      .get() as { n: number };
    return row.n;
  });

  // Catalog
  ipcMain.handle(
    "catalog:sync",
    (_e, opts: { apiBase: string; accessToken: string; tenantId?: string | null; force?: boolean }) =>
      syncCatalog(opts),
  );
  ipcMain.handle("catalog:search", (_e, query: string, limit?: number) =>
    searchProducts(query, limit),
  );
  ipcMain.handle("catalog:list", (_e, limit?: number) => listProducts(limit));
  ipcMain.handle("catalog:by-barcode", (_e, barcode: string) => productByBarcode(barcode));
  ipcMain.handle("catalog:count", () => productsCount());
  // FEFO: nearest-expiry in-stock batch for a batch-tracked product.
  ipcMain.handle(
    "catalog:nearest-batch",
    (_e, productId: string, branchId?: string | null) =>
      nearestExpiryBatch(productId, branchId),
  );
  ipcMain.handle(
    "catalog:batches",
    (_e, productId: string, branchId?: string | null) =>
      batchesForProduct(productId, branchId),
  );

  // Sales — Phase 2
  ipcMain.handle(
    "sales:persist-invoice",
    (
      _e,
      args: {
        invoice: PosInvoiceInput;
        items: PosSaleItemInput[];
        payments: PosPaymentInput[];
        is_held?: boolean;
        held_label?: string | null;
      },
    ) => {
      persistInvoice(args);
      return { ok: true };
    },
  );
  ipcMain.handle("sales:list", (_e, opts: { held?: boolean; limit?: number } = {}) =>
    listInvoices(opts),
  );
  ipcMain.handle("sales:get", (_e, invoice_id: string) => getInvoiceWithLines(invoice_id));
  ipcMain.handle("sales:hold", (_e, invoice_id: string, label: string) => {
    holdInvoice(invoice_id, label);
    return { ok: true };
  });
  ipcMain.handle("sales:recall", (_e, invoice_id: string) => {
    recallInvoice(invoice_id);
    return { ok: true };
  });
  ipcMain.handle("sales:delete-held", (_e, invoice_id: string) => {
    deleteHeldInvoice(invoice_id);
    return { ok: true };
  });
  ipcMain.handle(
    "sales:set-fbr-fields",
    (
      _e,
      args: {
        invoice_id: string;
        fbr_invoice_number: string;
        fbr_qr_payload: string | null;
        fbr_validated_at: string | null;
      },
    ) => {
      setInvoiceFbrFields(args);
      return { ok: true };
    },
  );

  // Cash sessions
  ipcMain.handle("session:open", (_e, payload: PosCashSession) => {
    openCashSession(payload);
    return { ok: true };
  });
  ipcMain.handle("session:current", (_e, terminal_id: string) => getOpenSession(terminal_id));
  ipcMain.handle("session:totals", (_e, session_id: string) => totalsForSession(session_id));
  ipcMain.handle(
    "session:close",
    (
      _e,
      id: string,
      args: {
        closed_at: string;
        closed_with_amount: string;
        expected_amount: string;
        variance: string;
        variance_reason: string;
      },
    ) => {
      closeCashSession(id, args);
      return { ok: true };
    },
  );

  // Printer + drawer
  ipcMain.handle("printer:print-receipt", async (_e, payload) => printReceipt(payload));
  ipcMain.handle("printer:print-kot", async (_e, payload) => printKOT(payload));
  ipcMain.handle("drawer:open", async () => openCashDrawer());

  // Customer-facing display (second monitor). Returns success=false when
  // no secondary display is attached so the renderer can fall back
  // gracefully.
  ipcMain.handle("customerDisplay:post", (_e, payload) => {
    const ok = postToCustomerDisplay(payload);
    return { success: ok };
  });

  // Phase 3 — sync worker bridge
  ipcMain.handle(
    "sync:set-tokens",
    (_e, accessToken: string | null, refreshToken: string | null) => {
      setAuthTokens(accessToken, refreshToken);
      return { ok: true };
    },
  );
  ipcMain.handle("sync:kick", () => {
    kickWorker();
    return { ok: true };
  });
  ipcMain.handle("sync:expedite", () => {
    expediteWorker();
    return { ok: true };
  });
  ipcMain.handle("sync:status", () => currentStatus());
  ipcMain.handle("sync:retry-failed", () => ({ retried: manualRetryFailed() }));
  ipcMain.handle("sync:list-pending", (_e, limit?: number) => listPendingSync(limit));
  ipcMain.handle("sync:retry-row", (_e, id: number) => ({ retried: retryQueueRowById(id) }));

  // Push sync status changes to all renderer windows.
  subscribe((s) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send("sync:status-changed", s);
    }
  });

  // Phase 3 — local invoice numbering
  ipcMain.handle(
    "numbering:next",
    (_e: IpcMainInvokeEvent, args: { branchCode: string; terminalIndex: number }) =>
      nextInvoiceNumber(args),
  );
}
