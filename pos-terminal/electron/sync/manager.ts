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

import { getDb } from "../db/client";

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
    path.resolve(__dirname, "db/schema.sql"),
    path.resolve(__dirname, "../electron/db/schema.sql"),
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
      // Persist the new tokens locally so the renderer's next reload sees them.
      const access = m.accessToken as string | null;
      const refresh = m.refreshToken as string | null;
      if (access) {
        getDb()
          .prepare(
            `INSERT INTO kv_meta(key, value, updated_at) VALUES('access_token', ?, CURRENT_TIMESTAMP)
             ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
          )
          .run(access);
      }
      if (refresh) {
        getDb()
          .prepare(
            `INSERT INTO kv_meta(key, value, updated_at) VALUES('refresh_token', ?, CURRENT_TIMESTAMP)
             ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
          )
          .run(refresh);
      }
    }
  });

  worker.postMessage({
    type: "init",
    dbPath: opts.dbPath,
    apiBase: opts.apiBase,
    schemaPath,
  });
}

export function setAuthTokens(accessToken: string | null, refreshToken: string | null) {
  if (!worker) return;
  worker.postMessage({ type: "auth", accessToken, refreshToken });
}

export function kickWorker() {
  if (!worker) return;
  worker.postMessage({ type: "kick" });
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
