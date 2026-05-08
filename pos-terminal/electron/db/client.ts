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
  return db;
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
