-- POS-side SQLite schema. Mirrors what the POS terminal needs locally.
--
-- Phase 0: outbound_queue, kv_meta, cached_users.
-- Phase 1: products, categories, stock_levels (read-only catalog mirror)
--          + FTS5 virtual table over products for fast search.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------------------
-- Phase 0
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS outbound_queue (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_uuid     TEXT NOT NULL UNIQUE,
  entity_type     TEXT NOT NULL,
  entity_id       TEXT NOT NULL,
  action          TEXT NOT NULL,
  payload         TEXT NOT NULL,
  attempt_count   INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  last_error      TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
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
  pin_hash          TEXT,
  last_synced_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Phase 1 — read-only catalog mirror + FTS index
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS categories (
  id            TEXT PRIMARY KEY,
  parent_id     TEXT,
  name          TEXT NOT NULL,
  name_ur       TEXT,
  display_order INTEGER NOT NULL DEFAULT 0,
  color         TEXT,
  icon          TEXT,
  is_active     INTEGER NOT NULL DEFAULT 1,
  updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id               TEXT PRIMARY KEY,
  category_id      TEXT,
  sku              TEXT NOT NULL,
  barcode          TEXT,
  name             TEXT NOT NULL,
  name_ur          TEXT,
  uom_code         TEXT NOT NULL,
  tax_rate_id      TEXT,
  is_taxable       INTEGER NOT NULL DEFAULT 1,
  sale_price       TEXT NOT NULL,
  retail_price     TEXT,
  min_sale_price   TEXT,
  max_discount_pct TEXT,
  is_weighable     INTEGER NOT NULL DEFAULT 0,
  image_url        TEXT,
  is_active        INTEGER NOT NULL DEFAULT 1,
  updated_at       TEXT NOT NULL,
  deleted_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_products_barcode
  ON products(barcode) WHERE barcode IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_products_active
  ON products(is_active) WHERE deleted_at IS NULL;

-- FTS5 — content='' means it's a manually-managed external content table.
-- Sync writes both products and products_fts; deletes from both.
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
  id UNINDEXED, name, name_ur, sku, barcode
);

CREATE TABLE IF NOT EXISTS stock_levels (
  product_id     TEXT NOT NULL,
  branch_id      TEXT NOT NULL,
  quantity       TEXT NOT NULL DEFAULT '0',
  reorder_level  TEXT,
  updated_at     TEXT NOT NULL,
  PRIMARY KEY (product_id, branch_id)
);

CREATE TABLE IF NOT EXISTS meta_sync (
  entity         TEXT PRIMARY KEY,
  last_synced_at TEXT NOT NULL,
  cursor         TEXT
);
