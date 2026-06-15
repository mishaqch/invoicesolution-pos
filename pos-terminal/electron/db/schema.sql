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
  hs_code          TEXT,
  is_taxable       INTEGER NOT NULL DEFAULT 1,
  sale_price       TEXT NOT NULL,
  retail_price     TEXT,
  min_sale_price   TEXT,
  max_discount_pct TEXT,
  is_third_schedule INTEGER NOT NULL DEFAULT 0,
  sale_type        TEXT NOT NULL DEFAULT 'Goods at standard rate (default)',
  is_weighable     INTEGER NOT NULL DEFAULT 0,
  is_batch_tracked INTEGER NOT NULL DEFAULT 0,
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

-- Product batches (pharmacy / date-sensitive goods). Mirrored from the server
-- as a FULL snapshot each catalog sync (the server sends every in-stock batch
-- for batch-tracked products). FEFO at sale time picks the soonest-expiry batch
-- with stock. current_quantity is the server's view; offline sales decrement a
-- local working copy via the cart, reconciled on next sync.
CREATE TABLE IF NOT EXISTS product_batches (
  id               TEXT PRIMARY KEY,
  product_id       TEXT NOT NULL,
  batch_number     TEXT NOT NULL,
  expiry_date      TEXT,
  current_quantity TEXT NOT NULL DEFAULT '0',
  branch_id        TEXT
);
CREATE INDEX IF NOT EXISTS idx_batches_product
  ON product_batches(product_id, expiry_date);

CREATE TABLE IF NOT EXISTS meta_sync (
  entity         TEXT PRIMARY KEY,
  last_synced_at TEXT NOT NULL,
  cursor         TEXT
);

-- ---------------------------------------------------------------------------
-- Phase 2 — invoices, sale_items, payments, customers, cash_sessions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS customers (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  phone             TEXT,
  email             TEXT,
  cnic              TEXT,
  ntn               TEXT,
  registration_type TEXT NOT NULL DEFAULT 'unregistered',
  province          TEXT,
  store_credit      TEXT NOT NULL DEFAULT '0',
  current_balance   TEXT NOT NULL DEFAULT '0',
  is_active         INTEGER NOT NULL DEFAULT 1,
  updated_at        TEXT NOT NULL,
  deleted_at        TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS customers_fts USING fts5(
  id UNINDEXED, name, phone, cnic
);

CREATE TABLE IF NOT EXISTS cash_sessions (
  id                  TEXT PRIMARY KEY,
  branch_id           TEXT NOT NULL,
  terminal_id         TEXT NOT NULL,
  cashier_id          TEXT NOT NULL,
  opened_at           TEXT NOT NULL,
  opened_with_amount  TEXT NOT NULL,
  closed_at           TEXT,
  closed_with_amount  TEXT,
  expected_amount     TEXT,
  variance            TEXT,
  variance_reason     TEXT,
  total_sales         TEXT NOT NULL DEFAULT '0',
  cash_in             TEXT NOT NULL DEFAULT '0',
  cash_out            TEXT NOT NULL DEFAULT '0',
  status              TEXT NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS idx_cash_sessions_open
  ON cash_sessions(terminal_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS invoices (
  id                       TEXT PRIMARY KEY,
  client_uuid              TEXT NOT NULL UNIQUE,
  local_invoice_number     TEXT NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'pending_sync',
  invoice_date             TEXT NOT NULL,

  customer_id              TEXT,
  buyer_name               TEXT,
  buyer_phone              TEXT,
  buyer_ntn_cnic           TEXT,
  buyer_registration_type  TEXT,

  branch_id                TEXT NOT NULL,
  terminal_id              TEXT NOT NULL,
  cashier_id               TEXT NOT NULL,
  cash_session_id          TEXT,

  subtotal                 TEXT NOT NULL,
  discount_total           TEXT NOT NULL DEFAULT '0',
  tax_total                TEXT NOT NULL DEFAULT '0',
  grand_total              TEXT NOT NULL,
  paid_total               TEXT NOT NULL DEFAULT '0',
  change_given             TEXT NOT NULL DEFAULT '0',

  is_held                  INTEGER NOT NULL DEFAULT 0,
  held_label               TEXT,

  -- Populated once the central server reports PRAL validation back to us.
  -- These are the source of truth for printing an FBR-compliant receipt
  -- (number + scannable QR) even when reprinting offline. NULL until valid.
  fbr_invoice_number       TEXT,
  fbr_qr_payload           TEXT,
  fbr_validated_at         TEXT,

  notes                    TEXT,
  created_at               TEXT NOT NULL,
  updated_at               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoices_held ON invoices(is_held) WHERE is_held = 1;
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_session ON invoices(cash_session_id);

CREATE TABLE IF NOT EXISTS sale_items (
  id                TEXT PRIMARY KEY,
  invoice_id        TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  line_number       INTEGER NOT NULL,
  product_id        TEXT NOT NULL,
  product_name      TEXT NOT NULL,
  product_sku       TEXT NOT NULL,
  uom_code          TEXT NOT NULL,
  hs_code           TEXT,
  quantity          TEXT NOT NULL,
  unit_price        TEXT NOT NULL,
  discount_pct      TEXT NOT NULL DEFAULT '0',
  discount_amount   TEXT NOT NULL DEFAULT '0',
  tax_rate          TEXT NOT NULL DEFAULT '0',
  tax_amount        TEXT NOT NULL DEFAULT '0',
  line_total        TEXT NOT NULL,
  notes             TEXT,
  -- FEFO batch this line drew stock from (pharmacy / batch-tracked goods).
  -- NULL for ordinary products. Carried into the checkout sync payload so the
  -- server records the sale movement against the right batch.
  batch_id          TEXT,
  -- Restaurant: JSON array of chosen modifiers + kitchen note (for reprint).
  modifiers         TEXT,
  item_note         TEXT,
  UNIQUE(invoice_id, line_number)
);

CREATE TABLE IF NOT EXISTS payments (
  id              TEXT PRIMARY KEY,
  invoice_id      TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  payment_method  TEXT NOT NULL,
  amount          TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'completed',
  created_at      TEXT NOT NULL
);
