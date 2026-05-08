-- POS-side SQLite schema. Mirrors what the POS terminal needs locally.
-- Schema additions land per phase. Phase 0 includes only:
--   1. outbound_queue (verbatim from DATABASE_SCHEMA.md §10)
--   2. kv_meta — small key/value bag for tokens, terminal_id, etc.
--   3. cached_users — assigned cashiers for offline PIN login (populated in
--      Phase 3 when sync exists). Phase 0 PIN login stays online-only.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS outbound_queue (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_uuid     TEXT NOT NULL UNIQUE,
  entity_type     TEXT NOT NULL,
  entity_id       TEXT NOT NULL,
  action          TEXT NOT NULL,
  payload         TEXT NOT NULL,                       -- JSON string
  attempt_count   INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,                       -- ISO datetime
  last_error      TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',     -- pending | sent | failed | cancelled
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_queue_pending
  ON outbound_queue(next_attempt_at)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS kv_meta (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cached_users (
  id                TEXT PRIMARY KEY,
  email             TEXT NOT NULL UNIQUE,
  full_name         TEXT NOT NULL,
  role              TEXT NOT NULL,
  pin_hash          TEXT,                              -- hashed; populated by sync from server
  last_synced_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
