/**
 * better-sqlite3 wrapper. Owned by the Electron main process; the renderer
 * never imports this directly — IPC bridges everything.
 */

import Database from "better-sqlite3";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

let db: Database.Database | null = null;

export function openDb(dbPath: string): Database.Database {
  if (db) return db;
  db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  applySchema(db);
  migrate(db);
  return db;
}

/**
 * Idempotent column adds for DBs created before a column existed. `schema.sql`
 * uses CREATE TABLE IF NOT EXISTS, so a pre-existing terminal never picks up
 * new columns from the schema file alone. ALTER TABLE ADD COLUMN is cheap and
 * we guard each with PRAGMA table_info so re-running is a no-op.
 *
 * Keep this in sync with worker.ts, which opens the same DB independently.
 */
export function migrate(connection: Database.Database): void {
  addColumnIfMissing(connection, "invoices", "fbr_invoice_number", "TEXT");
  addColumnIfMissing(connection, "invoices", "fbr_qr_payload", "TEXT");
  addColumnIfMissing(connection, "invoices", "fbr_validated_at", "TEXT");
  // hs_code reaches the terminal so a SCANNED sale carries a valid FBR HS code.
  // is_third_schedule drives MRP-based tax for 3rd-schedule items (cigarettes).
  addColumnIfMissing(connection, "products", "hs_code", "TEXT");
  addColumnIfMissing(connection, "products", "is_third_schedule", "INTEGER NOT NULL DEFAULT 0");
  // FBR sale type (PRAL transtypecode) — the terminal carries it so a sale's
  // line submits the right saleType. Server falls back to product.sale_type if
  // the terminal omits it, so pre-update terminals stay correct.
  addColumnIfMissing(connection, "products", "sale_type", "TEXT NOT NULL DEFAULT 'Goods at standard rate (default)'");
  // Pharmacy FEFO: which products track stock per batch (so a sale picks the
  // soonest-expiry batch). The product_batches table itself is created by
  // schema.sql (CREATE TABLE IF NOT EXISTS runs on every open).
  addColumnIfMissing(connection, "products", "is_batch_tracked", "INTEGER NOT NULL DEFAULT 0");
  // FEFO: the batch a sale line drew from (NULL for ordinary products).
  addColumnIfMissing(connection, "sale_items", "batch_id", "TEXT");
  // Restaurant: chosen modifiers (JSON) + kitchen note on a sale line.
  addColumnIfMissing(connection, "sale_items", "modifiers", "TEXT");
  addColumnIfMissing(connection, "sale_items", "item_note", "TEXT");
}

function addColumnIfMissing(
  connection: Database.Database,
  table: string,
  column: string,
  type: string,
): void {
  const cols = connection.prepare(`PRAGMA table_info(${table})`).all() as {
    name: string;
  }[];
  if (cols.some((c) => c.name === column)) return;
  connection.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${type}`);
}

function applySchema(connection: Database.Database) {
  // Resolve schema.sql across dev AND the packaged layout. In a packaged
  // build __dirname is `…/app.asar/out/main`, while electron-builder's `files`
  // glob packages the source file to `…/app.asar/electron/db/schema.sql`
  // (i.e. two levels up from out/main, then electron/db). The old candidates
  // missed that location, so openDb() threw at launch on Windows and the app
  // died before showing a window. Order: dev source, packaged asar root,
  // legacy guesses, cwd.
  const candidates = [
    path.resolve(__dirname, "db/schema.sql"),                    // dev: electron/db
    path.resolve(__dirname, "../../electron/db/schema.sql"),     // packaged: out/main → asar root → electron/db
    path.resolve(__dirname, "../electron/db/schema.sql"),        // legacy layout
    path.resolve(process.resourcesPath ?? "", "app.asar/electron/db/schema.sql"),
    path.resolve(process.resourcesPath ?? "", "electron/db/schema.sql"),
    path.resolve(process.cwd(), "electron/db/schema.sql"),
  ];
  const schemaPath = candidates.find((p) => existsSync(p));
  if (!schemaPath) {
    throw new Error("schema.sql not found in any expected location: " + candidates.join(", "));
  }
  const sql = readFileSync(schemaPath, "utf-8");
  connection.exec(sql);
}

export function getDb(): Database.Database {
  if (!db) throw new Error("Database not initialized. Call openDb() first.");
  return db;
}

export function setMeta(key: string, value: string): void {
  getDb()
    .prepare(
      "INSERT INTO kv_meta(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) " +
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
    )
    .run(key, value);
}

export function getMeta(key: string): string | null {
  const row = getDb().prepare("SELECT value FROM kv_meta WHERE key = ?").get(key) as
    | { value: string }
    | undefined;
  return row?.value ?? null;
}
