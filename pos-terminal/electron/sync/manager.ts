/**
 * Sync manager — owned by the main process.
 *
 * Spawns the worker utilityProcess, forwards auth tokens to it, and
 * exposes the worker's status messages back to the renderer via IPC
 * (window.api.sync.subscribe / status / kick).
 */

import { utilityProcess, type UtilityProcess } from "electron";
import { existsSync } from "node:fs";
import path from "node:path";

import { getDb, getMeta } from "../db/client";

interface WorkerStatus {
  counts: { pending: number; ok: number; failed: number };
  last_processed_at: string | null;
  last_error: string | null;
}

let worker: UtilityProcess | null = null;
let lastStatus: WorkerStatus = {
  counts: { pending: 0, ok: 0, failed: 0 },
  last_processed_at: null,
  last_error: null,
};
const subscribers = new Set<(s: WorkerStatus) => void>();

export function startSyncWorker(opts: { dbPath: string; apiBase: string }) {
  if (worker) return;

  const candidates = [
    path.resolve(__dirname, "sync/worker.cjs"),
    path.resolve(__dirname, "../sync/worker.cjs"),
    path.resolve(__dirname, "../sync/worker.js"),
    path.resolve(__dirname, "sync/worker.js"),
  ];
  const workerPath = candidates.find((p) => existsSync(p));
  if (!workerPath) {
    // Fail loudly — a missing worker means EVERY sale will pile up in
    // the local outbound queue and never reach the backend. The build
    // config (electron.vite.config.ts) must include
    //   "sync/worker": "electron/sync/worker.ts"
    // in the main entry inputs so electron-vite produces worker.cjs.
    // We used to console.error here and continue silently — that hid
    // the bug for weeks. Throwing surfaces the issue at app startup.
    const msg =
      "[sync] worker entry not found in any of:\n  " +
      candidates.join("\n  ") +
      "\n\nElectron-vite must bundle electron/sync/worker.ts as sync/worker.cjs.\n" +
      "If you just rebuilt: rerun `npm run build` or restart `npm run dev`.";
    // eslint-disable-next-line no-console
    console.error(msg);
    throw new Error(msg);
  }

  // The worker reapplies the schema on init in case of a fresh DB; the main
  // process already has a handle, so SQLite WAL allows shared reads/writes.
  const schemaCandidates = [
    path.resolve(__dirname, "db/schema.sql"),                  // dev
    path.resolve(__dirname, "../../electron/db/schema.sql"),   // packaged: out/main → asar root → electron/db
    path.resolve(__dirname, "../electron/db/schema.sql"),      // legacy
    path.resolve(process.resourcesPath ?? "", "app.asar/electron/db/schema.sql"),
  ];
  const schemaPath = schemaCandidates.find((p) => existsSync(p)) ?? schemaCandidates[0];

  worker = utilityProcess.fork(workerPath, [], {
    serviceName: "pos-sync-worker",
    stdio: "inherit",
  });

  worker.on("message", (raw: unknown) => {
    const m = raw as { type: string; [k: string]: unknown };
    if (m.type === "status") {
      lastStatus = m as unknown as WorkerStatus;
      for (const cb of subscribers) cb(lastStatus);
    } else if (m.type === "log") {
      // eslint-disable-next-line no-console
      console.log(`[sync ${m.level}] ${m.message}`);
    } else if (m.type === "tokens_refreshed") {
      // Persist the refreshed tokens locally so the renderer's next reload — and
      // main-process readers (fiscalize, kot-relay) — see them.
      persistTokens(m.accessToken as string | null, m.refreshToken as string | null);
    }
  });

  worker.postMessage({
    type: "init",
    dbPath: opts.dbPath,
    apiBase: opts.apiBase,
    schemaPath,
  });

  // RESTORE the auth tokens from kv_meta.
  //
  // The renderer only pushes tokens on sign-in (session.ts), and it keeps
  // them in memory ONLY — partialize() deliberately persists just
  // user/tenant/role, never access/refresh. So after every app restart the
  // cashier still LOOKS signed in (user restored from disk) while the sync
  // worker holds no token at all: processRow() logs "no access token;
  // skipping" and never POSTs.
  //
  // That is why a charged sale was enqueued locally and then sat in
  // outbound_queue forever, leaving the paid order on the Open Orders screen:
  // /api/sync/invoices/ was never called ONCE in the entire nginx history,
  // while /api/restaurant/orders/ (renderer, live in-memory token) worked fine.
  //
  // setAuthTokens() already persists both tokens to kv_meta at login, so they
  // are here on disk — the worker just never read them back. Hand them over
  // now; if the access token has expired the worker's own 401 handler
  // refreshes it with the refresh token.
  try {
    const access = getMeta("access_token");
    const refresh = getMeta("refresh_token");
    if (access || refresh) {
      worker.postMessage({ type: "auth", accessToken: access, refreshToken: refresh });
    }
  } catch {
    // A missing kv_meta row is not fatal — the next sign-in supplies tokens.
  }
}

/**
 * Persist the auth tokens into kv_meta so main-process readers (fiscalize,
 * kot-relay) and the renderer's next reload can pick them up. Shared by the
 * login path (setAuthTokens) and the worker's token-refresh handler.
 */
function persistTokens(accessToken: string | null, refreshToken: string | null): void {
  if (accessToken) {
    getDb()
      .prepare(
        `INSERT INTO kv_meta(key, value, updated_at) VALUES('access_token', ?, CURRENT_TIMESTAMP)
         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
      )
      .run(accessToken);
  }
  if (refreshToken) {
    getDb()
      .prepare(
        `INSERT INTO kv_meta(key, value, updated_at) VALUES('refresh_token', ?, CURRENT_TIMESTAMP)
         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
      )
      .run(refreshToken);
  }
}

export function setAuthTokens(accessToken: string | null, refreshToken: string | null) {
  // Persist IMMEDIATELY (at login) — don't wait for the worker's first token
  // refresh. Without this, kot-relay/fiscalize would find no access_token in
  // kv_meta until a refresh happened, so a freshly-signed-in terminal wouldn't
  // relay KOTs for a while after launch.
  persistTokens(accessToken, refreshToken);
  if (!worker) return;
  worker.postMessage({ type: "auth", accessToken, refreshToken });
}

export function kickWorker() {
  if (!worker) return;
  worker.postMessage({ type: "kick" });
}

// Connectivity restored → tell the worker to reset pending rows' backoff and
// retry immediately. Use this (not kickWorker) on online/resume transitions so
// rows sitting in backoff don't wait out their timer once the link is back.
export function expediteWorker() {
  if (!worker) return;
  worker.postMessage({ type: "expedite" });
}

export function stopSyncWorker() {
  if (!worker) return;
  worker.postMessage({ type: "stop" });
  worker = null;
}

export function currentStatus(): WorkerStatus {
  return lastStatus;
}

export function subscribe(cb: (s: WorkerStatus) => void): () => void {
  subscribers.add(cb);
  cb(lastStatus);
  return () => subscribers.delete(cb);
}

export function manualRetryFailed(): number {
  // Reset every failed row to pending now. Returns the number reset.
  const result = getDb()
    .prepare(
      `UPDATE outbound_queue SET status = 'pending',
        next_attempt_at = CURRENT_TIMESTAMP, last_error = NULL
       WHERE status = 'failed'`,
    )
    .run();
  if (result.changes > 0) kickWorker();
  return result.changes;
}

// Retry one specific queue row now (per-row "Retry" on the pending-sync list).
// Works for both 'failed' and 'pending' rows; clears the backoff and kicks.
export function retryQueueRowById(id: number): number {
  const result = getDb()
    .prepare(
      `UPDATE outbound_queue SET status = 'pending',
        next_attempt_at = CURRENT_TIMESTAMP, attempt_count = 0, last_error = NULL
       WHERE id = ? AND status IN ('failed', 'pending', 'sent')`,
    )
    .run(id);
  if (result.changes > 0) kickWorker();
  return result.changes;
}
