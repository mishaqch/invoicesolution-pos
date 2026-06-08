/**
 * Sync worker — runs as an Electron utilityProcess.
 *
 * Loops:
 *   1. Pick the oldest pending row whose next_attempt_at <= now().
 *   2. Mark sent_at, POST it.
 *   3. On success → status='sent'; on 4xx → status='failed' (no retry);
 *      on transient error → bump attempt_count, set next_attempt_at via
 *      the backoff schedule.
 *
 * Serial processing: never more than one in-flight POST per worker. See
 * the Phase 3 plan for the justification (ordering, retry storms, JWT).
 *
 * Crash recovery: any 'sent' rows on startup are re-sent. Server is
 * idempotent on client_uuid.
 *
 * Communication with the renderer goes through the main process via
 * postMessage on parentPort. Message types:
 *   { type: 'status', counts: {...}, last_processed_at, last_error }
 *   { type: 'log', level: 'info' | 'warn' | 'error', message: string }
 */

import Database from "better-sqlite3";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { MAX_ATTEMPTS, backoffSeconds } from "./backoff";

interface InitMessage {
  type: "init";
  dbPath: string;
  apiBase: string;
  schemaPath: string;
}

interface AuthMessage {
  type: "auth";
  accessToken: string | null;
  refreshToken: string | null;
}

interface RefreshTokenResponse {
  accessToken: string;
  refreshToken?: string | null;
}

type MsgIn = InitMessage | AuthMessage | { type: "kick" } | { type: "stop" };

interface QueueRow {
  id: number;
  client_uuid: string;
  entity_type: "invoice" | "customer" | "stock_adjustment";
  entity_id: string;
  action: string;
  payload: string;
  attempt_count: number;
  status: string;
}

let db: Database.Database | null = null;
let apiBase = "";
let accessToken: string | null = null;
let refreshToken: string | null = null;
let stopped = false;
let kickPromise: { resolve: () => void } | null = null;
let lastProcessedAt: string | null = null;
let lastError: string | null = null;

// Electron's utilityProcess.fork() exposes the parent-port on
// `process.parentPort` (NOT on globalThis — that's a Worker-thread
// convention, not utilityProcess). Using the wrong path causes the
// child to crash at module-load with "worker requires parentPort".
interface ParentPort {
  postMessage: (m: unknown) => void;
  on: (event: string, cb: (m: unknown) => void) => void;
}
const maybePort = (process as unknown as {
  parentPort?: ParentPort;
}).parentPort;

if (!maybePort) {
  // Should never happen — utilityProcess always provides parentPort.
  throw new Error("worker requires process.parentPort (utilityProcess child)");
}
// Narrowed reference; downstream code uses the non-nullable binding.
const port: ParentPort = maybePort;

port.on("message", (raw: unknown) => {
  const m = raw as MsgIn;
  if (m.type === "init") {
    init(m);
  } else if (m.type === "auth") {
    accessToken = m.accessToken;
    refreshToken = m.refreshToken;
    log("info", `auth tokens updated (access: ${accessToken ? "set" : "null"})`);
    kick();
  } else if (m.type === "kick") {
    kick();
  } else if (m.type === "stop") {
    stopped = true;
    kick();
  }
});

function init(m: InitMessage) {
  apiBase = m.apiBase.replace(/\/$/, "");
  db = new Database(m.dbPath);
  db.pragma("journal_mode = WAL");

  if (existsSync(m.schemaPath)) {
    db.exec(readFileSync(m.schemaPath, "utf-8"));
  }

  // Idempotent column adds for DBs created before these columns existed.
  // schema.sql uses CREATE TABLE IF NOT EXISTS so a pre-existing terminal
  // never gets new columns from the file alone. Mirror of client.ts migrate().
  for (const [col, type] of [
    ["fbr_invoice_number", "TEXT"],
    ["fbr_qr_payload", "TEXT"],
    ["fbr_validated_at", "TEXT"],
  ] as const) {
    const cols = db.prepare(`PRAGMA table_info(invoices)`).all() as { name: string }[];
    if (!cols.some((c) => c.name === col)) {
      db.exec(`ALTER TABLE invoices ADD COLUMN ${col} ${type}`);
    }
  }
  // FEFO: batch_id on sale_items (the worker reads sale_items to build the
  // checkout sync payload, so it needs the column on a pre-existing DB).
  {
    const cols = db.prepare(`PRAGMA table_info(sale_items)`).all() as { name: string }[];
    if (!cols.some((c) => c.name === "batch_id")) {
      db.exec(`ALTER TABLE sale_items ADD COLUMN batch_id TEXT`);
    }
  }

  // Crash recovery: 'sent' rows mean we POSTed but never recorded the ack.
  // Reset them to 'pending' so the loop picks them up. Server idempotency
  // makes the re-send safe.
  db.prepare(`UPDATE outbound_queue SET status = 'pending' WHERE status = 'sent'`).run();

  log("info", "worker initialized");
  void runForever();
}

async function runForever() {
  while (!stopped) {
    const row = pickRow();
    if (row === null) {
      // Sleep until kicked or until the soonest next_attempt_at.
      const ms = msUntilNextAttempt() ?? 30_000;
      await waitForKickOrTimeout(ms);
      continue;
    }
    await processRow(row);
    publishStatus();
  }
}

function pickRow(): QueueRow | null {
  const now = new Date().toISOString();
  const row = getDb()
    .prepare(
      `SELECT id, client_uuid, entity_type, entity_id, action, payload,
              attempt_count, status
       FROM outbound_queue
       WHERE status = 'pending' AND next_attempt_at <= ?
       ORDER BY id LIMIT 1`,
    )
    .get(now) as QueueRow | undefined;
  return row ?? null;
}

function msUntilNextAttempt(): number | null {
  const row = getDb()
    .prepare(
      `SELECT next_attempt_at FROM outbound_queue
       WHERE status = 'pending'
       ORDER BY datetime(next_attempt_at) ASC
       LIMIT 1`,
    )
    .get() as { next_attempt_at: string } | undefined;
  if (!row) return null;
  const t = new Date(row.next_attempt_at).getTime();
  return Math.max(0, t - Date.now());
}

async function processRow(row: QueueRow) {
  if (!accessToken) {
    log("warn", "no access token; skipping");
    await waitForKickOrTimeout(15_000);
    return;
  }

  // Pre-mark as 'sent' so a crash mid-POST shows up clearly in logs.
  getDb()
    .prepare(`UPDATE outbound_queue SET status = 'sent' WHERE id = ?`)
    .run(row.id);

  const url = `${apiBase}${endpointFor(row.entity_type)}`;
  const payload = JSON.parse(row.payload);

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        "Idempotency-Key": row.client_uuid,
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(30_000),
    });
  } catch (err) {
    transientFailure(row, `network: ${(err as Error).message}`);
    return;
  }

  if (response.ok) {
    let body: { sync_status?: string } = {};
    try { body = await response.json(); } catch {}
    finalizeSent(row, body.sync_status === "duplicate" ? "duplicate" : "ok");
    return;
  }

  if (response.status === 401) {
    log("warn", "401 — attempting token refresh");
    const refreshed = await tryRefreshToken();
    if (!refreshed) {
      // Mark this row as still pending; pause briefly.
      getDb().prepare(`UPDATE outbound_queue SET status='pending' WHERE id=?`).run(row.id);
      port.postMessage({ type: "needs_login" });
      await waitForKickOrTimeout(60_000);
      return;
    }
    // Re-process this row immediately with the new token.
    getDb().prepare(`UPDATE outbound_queue SET status='pending' WHERE id=?`).run(row.id);
    return;
  }

  if (response.status >= 400 && response.status < 500) {
    let body: string;
    try { body = JSON.stringify(await response.json()); } catch { body = await response.text(); }
    permanentFailure(row, `${response.status}: ${body}`);
    return;
  }

  // 5xx → transient
  transientFailure(row, `${response.status}: server error`);
}

function endpointFor(entity_type: string): string {
  switch (entity_type) {
    case "invoice": return "/api/sync/invoices/";
    case "customer": return "/api/sync/customers/";
    default: return `/api/sync/${entity_type}s/`;
  }
}

function finalizeSent(row: QueueRow, kind: "ok" | "duplicate") {
  const now = new Date().toISOString();
  getDb()
    .prepare(`UPDATE outbound_queue SET status = 'ok', sent_at = ? WHERE id = ?`)
    .run(now, row.id);
  // After a successful sync, cascade local invoice status if applicable.
  if (row.entity_type === "invoice") {
    getDb()
      .prepare(`UPDATE invoices SET status = 'valid', updated_at = ? WHERE id = ?`)
      .run(now, row.entity_id);
  }
  lastProcessedAt = now;
  lastError = null;
  log("info", `synced ${row.entity_type} ${row.entity_id} (${kind})`);
}

function permanentFailure(row: QueueRow, message: string) {
  getDb()
    .prepare(
      `UPDATE outbound_queue SET status = 'failed', last_error = ? WHERE id = ?`,
    )
    .run(message, row.id);
  lastError = message;
  log("error", `permanent failure ${row.entity_type} ${row.entity_id}: ${message}`);
}

function transientFailure(row: QueueRow, message: string) {
  const next_attempt = row.attempt_count + 1;
  if (next_attempt >= MAX_ATTEMPTS) {
    permanentFailure(row, `max attempts: ${message}`);
    return;
  }
  const seconds = backoffSeconds(next_attempt) ?? 60;
  const next_at = new Date(Date.now() + seconds * 1000).toISOString();
  getDb()
    .prepare(
      `UPDATE outbound_queue SET status = 'pending',
        attempt_count = ?, next_attempt_at = ?, last_error = ?
       WHERE id = ?`,
    )
    .run(next_attempt, next_at, message, row.id);
  lastError = message;
  log("warn", `transient failure ${row.entity_type} ${row.entity_id}, retry in ${seconds}s: ${message}`);
}

async function tryRefreshToken(): Promise<boolean> {
  if (!refreshToken) return false;
  try {
    const resp = await fetch(`${apiBase}/api/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refreshToken }),
      signal: AbortSignal.timeout(15_000),
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as RefreshTokenResponse;
    accessToken = data.accessToken ?? null;
    if (data.refreshToken !== undefined) refreshToken = data.refreshToken ?? refreshToken;
    port.postMessage({ type: "tokens_refreshed", accessToken, refreshToken });
    return !!accessToken;
  } catch {
    return false;
  }
}

function publishStatus() {
  const counts = getDb()
    .prepare(
      `SELECT
         SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
         SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) AS ok,
         SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
       FROM outbound_queue`,
    )
    .get() as { pending: number; ok: number; failed: number };
  port.postMessage({
    type: "status",
    counts,
    last_processed_at: lastProcessedAt,
    last_error: lastError,
  });
}

function kick() {
  if (kickPromise) {
    kickPromise.resolve();
    kickPromise = null;
  }
}

function waitForKickOrTimeout(ms: number): Promise<void> {
  return new Promise<void>((resolve) => {
    let resolved = false;
    const handle = setTimeout(() => {
      if (resolved) return;
      resolved = true;
      kickPromise = null;
      resolve();
    }, ms);
    kickPromise = {
      resolve: () => {
        if (resolved) return;
        resolved = true;
        clearTimeout(handle);
        resolve();
      },
    };
  });
}

function getDb(): Database.Database {
  if (!db) throw new Error("DB not initialized");
  return db;
}

function log(level: "info" | "warn" | "error", message: string) {
  port.postMessage({ type: "log", level, message });
}
