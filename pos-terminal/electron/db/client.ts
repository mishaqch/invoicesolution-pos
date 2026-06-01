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
  // electron-vite builds main into dist-electron/main; resolve schema relative
  // to either the source path (dev) or the bundled location (prod).
  const candidates = [
    path.resolve(__dirname, "db/schema.sql"),
    path.resolve(__dirname, "../electron/db/schema.sql"),
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
