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

import { ipcMain, type IpcMainInvokeEvent, BrowserWindow } from "electron";

import { getDb, getMeta, setMeta } from "./db/client";
import { nextInvoiceNumber } from "./db/numbering";
import {
  currentStatus, kickWorker, manualRetryFailed, setAuthTokens, subscribe,
} from "./sync/manager";
import {
  closeCashSession,
  getInvoiceWithLines,
  getOpenSession,
  holdInvoice,
  listInvoices,
  openCashSession,
  persistInvoice,
  recallInvoice,
  totalsForSession,
  type PosCashSession,
  type PosInvoiceInput,
  type PosPaymentInput,
  type PosSaleItemInput,
} from "./db/sales";
import { listProducts, productsCount, searchProducts, syncCatalog } from "./db/sync";
import { openCashDrawer, printReceipt } from "./printer";
import { postToCustomerDisplay } from "./customer-display";

export function registerIpcHandlers() {
  // Meta
  ipcMain.handle("meta:get", (_e, key: string) => getMeta(key));
  ipcMain.handle("meta:set", (_e, key: string, value: string) => setMeta(key, value));

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
  ipcMain.handle("catalog:sync", (_e, opts: { apiBase: string; accessToken: string }) =>
    syncCatalog(opts),
  );
  ipcMain.handle("catalog:search", (_e, query: string, limit?: number) =>
    searchProducts(query, limit),
  );
  ipcMain.handle("catalog:list", (_e, limit?: number) => listProducts(limit));
  ipcMain.handle("catalog:count", () => productsCount());

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
  ipcMain.handle("sync:status", () => currentStatus());
  ipcMain.handle("sync:retry-failed", () => ({ retried: manualRetryFailed() }));

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
