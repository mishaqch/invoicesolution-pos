# Database Schema — Pakistan POS

> Complete schema for the Django backend. PostgreSQL 16. All money fields are `DECIMAL(14, 4)`. All timestamps are `TIMESTAMPTZ` (with timezone). All primary keys are `UUID` v7 except where noted (legacy/integer where it makes sense, like sequential invoice numbers).

## Conventions

- **Primary keys**: `id UUID DEFAULT gen_random_uuid() PRIMARY KEY`. UUIDv7 preferred (sortable by time) — implement via `pgcrypto` + small Python helper.
- **Timestamps on every table**: `created_at`, `updated_at` (auto-managed via trigger or Django `auto_now`).
- **Soft delete**: `deleted_at TIMESTAMPTZ NULL` instead of hard delete on user-facing records (products, customers, invoices). Filter at the queryset level.
- **Tenant scoping**: every table EXCEPT `tenants`, `users` (user can belong to multiple tenants), and global lookups (`hs_codes`, `units_of_measure`) carries `tenant_id UUID NOT NULL`. Composite indexes always lead with `tenant_id`.
- **Money**: `DECIMAL(14, 4)` for amounts (Pakistan rupees with 4 decimal precision for tax math). Display in PKR with 2 decimals.
- **Audit**: every meaningful state change writes a row to `audit_log`. The audit module reads no data — it only writes.

## Section 1 — Identity, tenancy, access

### `tenants`
The business that has subscribed to our POS.

```sql
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_name VARCHAR(255) NOT NULL,
  ntn VARCHAR(20) NOT NULL,                       -- National Tax Number
  strn VARCHAR(20),                               -- Sales Tax Registration Number (nullable; not all are STRN registered yet)
  cnic_owner VARCHAR(15),                         -- For sole proprietors
  business_type VARCHAR(50) NOT NULL,             -- 'sole_proprietor' | 'partnership' | 'private_ltd' | 'public_ltd' | 'aop'
  fbr_business_natures TEXT[],                    -- ['Retailer', 'Wholesaler'] etc.
  fbr_sector VARCHAR(50),                         -- 'FMCG' | 'Pharmaceuticals' | 'All Other Sectors' etc.
  province VARCHAR(20) NOT NULL,                  -- 'PUNJAB' | 'SINDH' | 'KP' | 'BALOCHISTAN' | 'ICT' | 'GB' | 'AJK'
  address TEXT,
  phone VARCHAR(20),
  email VARCHAR(255),
  logo_url TEXT,
  subscription_plan VARCHAR(50) NOT NULL DEFAULT 'starter',  -- starter | pro | enterprise
  subscription_status VARCHAR(20) NOT NULL DEFAULT 'trial',  -- trial | active | past_due | suspended | cancelled
  trial_ends_at TIMESTAMPTZ,
  next_billing_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ntn)
);
```

### `users`
A person. Can belong to multiple tenants (for accountants serving multiple shops).

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  phone VARCHAR(20) UNIQUE,
  full_name VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,             -- Argon2id
  pin_hash VARCHAR(255),                           -- 4–6 digit cashier PIN, also Argon2id
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_staff BOOLEAN NOT NULL DEFAULT FALSE,         -- Anthropic-side support staff
  last_login_at TIMESTAMPTZ,
  password_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  failed_login_count INT NOT NULL DEFAULT 0,
  locked_until TIMESTAMPTZ,
  preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',  -- 'en' | 'ur'
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `tenant_memberships`
Which user belongs to which tenant, and in what role.

```sql
CREATE TABLE tenant_memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(30) NOT NULL,                       -- 'owner' | 'manager' | 'cashier' | 'accountant' | 'auditor'
  branch_ids UUID[],                               -- if NULL or empty, has access to all branches
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  custom_permissions JSONB,                        -- per-user overrides on the role default
  invited_at TIMESTAMPTZ,
  joined_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, user_id)
);
CREATE INDEX idx_memberships_user ON tenant_memberships(user_id);
CREATE INDEX idx_memberships_tenant ON tenant_memberships(tenant_id) WHERE is_active = TRUE;
```

### `roles_permissions` (config — not a DB table, lives in code)
Default permission matrix per role. Codified in `backend/apps/accounts/permissions.py`. Highlights:

| Permission | Owner | Manager | Cashier | Accountant | Auditor |
|---|---|---|---|---|---|
| `sales.create` | ✓ | ✓ | ✓ | | |
| `sales.cancel.threshold_low` | ✓ | ✓ | ✓ | | |
| `sales.cancel.threshold_high` | ✓ | ✓ | | | |
| `inventory.adjust` | ✓ | ✓ | | | |
| `products.manage` | ✓ | ✓ | | | |
| `users.manage` | ✓ | | | | |
| `fbr.tokens.manage` | ✓ | | | | |
| `reports.view.all_branches` | ✓ | | | ✓ | ✓ |
| `reports.view.own_branch` | ✓ | ✓ | | ✓ | ✓ |
| `audit_log.view` | ✓ | | | ✓ | ✓ |
| `settings.business_profile` | ✓ | | | | |

---

## Section 2 — Locations & devices

### `branches`
A physical outlet.

```sql
CREATE TABLE branches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  code VARCHAR(20) NOT NULL,                       -- short code like "MAIN", "DHA-2"; used in invoice numbers
  address TEXT NOT NULL,
  city VARCHAR(100) NOT NULL,
  province VARCHAR(20) NOT NULL,
  phone VARCHAR(20),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  fbr_pos_id VARCHAR(50),                          -- POS ID assigned by FBR for this outlet (if Tier-1)
  receipt_header TEXT,                             -- override of tenant default
  receipt_footer TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  UNIQUE (tenant_id, code)
);
CREATE INDEX idx_branches_tenant ON branches(tenant_id) WHERE deleted_at IS NULL;
```

### `terminals`
A POS terminal device. Each Electron install registers as one.

```sql
CREATE TABLE terminals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  branch_id UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,                      -- "Counter 1", "Drive-thru"
  device_fingerprint VARCHAR(128) NOT NULL,        -- machine ID + install UUID
  os_version VARCHAR(50),
  app_version VARCHAR(20),
  printer_config JSONB DEFAULT '{}',               -- printer model, paper width, IP if network
  scanner_config JSONB DEFAULT '{}',
  drawer_config JSONB DEFAULT '{}',
  customer_display_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_seen_at TIMESTAMPTZ,
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (device_fingerprint)
);
CREATE INDEX idx_terminals_branch ON terminals(branch_id) WHERE is_active = TRUE;
```

### `cash_sessions`
A day-open / day-close cycle. One per terminal per day.

```sql
CREATE TABLE cash_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  branch_id UUID NOT NULL REFERENCES branches(id),
  terminal_id UUID NOT NULL REFERENCES terminals(id),
  cashier_id UUID NOT NULL REFERENCES users(id),
  opened_at TIMESTAMPTZ NOT NULL,
  opened_with_amount DECIMAL(14, 4) NOT NULL,      -- opening float
  closed_at TIMESTAMPTZ,
  closed_with_amount DECIMAL(14, 4),               -- declared cash count
  expected_amount DECIMAL(14, 4),                  -- system-computed
  variance DECIMAL(14, 4),                         -- closed - expected
  variance_reason TEXT,
  total_sales DECIMAL(14, 4) NOT NULL DEFAULT 0,
  total_returns DECIMAL(14, 4) NOT NULL DEFAULT 0,
  cash_in DECIMAL(14, 4) NOT NULL DEFAULT 0,
  cash_out DECIMAL(14, 4) NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'open',      -- 'open' | 'closed'
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cash_sessions_terminal_open ON cash_sessions(terminal_id) WHERE status = 'open';
CREATE INDEX idx_cash_sessions_tenant_date ON cash_sessions(tenant_id, opened_at DESC);
```

---

## Section 3 — Catalog

### `units_of_measure` (global lookup, no tenant_id)
```sql
CREATE TABLE units_of_measure (
  code VARCHAR(20) PRIMARY KEY,                    -- 'PCS', 'KG', 'GM', 'LTR', 'ML', 'BOX', 'DOZEN', 'PACK', 'METER'
  name_en VARCHAR(50) NOT NULL,
  name_ur VARCHAR(50),
  is_decimal_quantity BOOLEAN NOT NULL DEFAULT FALSE  -- KG/LTR allow 1.5; PCS doesn't
);
-- Seeded with ~20 standard Pakistani retail units.
```

### `hs_codes` (global lookup, no tenant_id)
```sql
CREATE TABLE hs_codes (
  code VARCHAR(15) PRIMARY KEY,                    -- '0101.2100' style
  description TEXT NOT NULL,
  default_tax_rate DECIMAL(5, 2),                  -- typical rate, can be overridden
  uom_default VARCHAR(20) REFERENCES units_of_measure(code),
  parent_code VARCHAR(15)                          -- for navigating the hierarchy
);
CREATE INDEX idx_hs_codes_description ON hs_codes USING gin (to_tsvector('english', description));
-- Seeded from FBR's published HS code list (~5000 entries).
```

### `tax_rates`
Tenant-specific overrides if needed; mostly references `hs_codes.default_tax_rate`.

```sql
CREATE TABLE tax_rates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(50) NOT NULL,                       -- 'Standard 18%', 'Reduced 8%', 'Zero rated', 'Exempt'
  rate DECIMAL(5, 2) NOT NULL,                     -- 18.00
  is_compound BOOLEAN NOT NULL DEFAULT FALSE,
  applies_to VARCHAR(20) NOT NULL DEFAULT 'goods',  -- 'goods' | 'services' | 'both'
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_rates_tenant ON tax_rates(tenant_id);
```

### `categories`
Hierarchical product categories.

```sql
CREATE TABLE categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  parent_id UUID REFERENCES categories(id) ON DELETE SET NULL,
  name VARCHAR(255) NOT NULL,
  name_ur VARCHAR(255),
  slug VARCHAR(255) NOT NULL,
  display_order INT NOT NULL DEFAULT 0,
  color VARCHAR(7),                                -- hex, for POS quick-pick buttons
  icon VARCHAR(50),                                -- lucide icon name
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, slug)
);
CREATE INDEX idx_categories_tenant ON categories(tenant_id) WHERE is_active = TRUE;
CREATE INDEX idx_categories_parent ON categories(parent_id);
```

### `products`
The master SKU.

```sql
CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  category_id UUID REFERENCES categories(id) ON DELETE SET NULL,
  name VARCHAR(255) NOT NULL,
  name_ur VARCHAR(255),
  description TEXT,
  sku VARCHAR(50) NOT NULL,                        -- internal SKU
  barcode VARCHAR(50),                             -- EAN/UPC, can be NULL for unbarcoded items
  hs_code VARCHAR(15) REFERENCES hs_codes(code),
  uom_code VARCHAR(20) NOT NULL REFERENCES units_of_measure(code),
  tax_rate_id UUID REFERENCES tax_rates(id),
  is_taxable BOOLEAN NOT NULL DEFAULT TRUE,
  cost_price DECIMAL(14, 4) NOT NULL DEFAULT 0,    -- last cost
  sale_price DECIMAL(14, 4) NOT NULL,              -- default selling price (excl. tax)
  retail_price DECIMAL(14, 4),                     -- printed retail / fixed notified value
  min_sale_price DECIMAL(14, 4),                   -- floor; cashier can't go below
  max_discount_pct DECIMAL(5, 2),                  -- ceiling on discount %
  reorder_level DECIMAL(14, 4),                    -- per-product low-stock threshold
  reorder_quantity DECIMAL(14, 4),
  is_serialized BOOLEAN NOT NULL DEFAULT FALSE,    -- track individual serial numbers (electronics)
  is_batch_tracked BOOLEAN NOT NULL DEFAULT FALSE, -- track batches (pharmacy)
  is_weighable BOOLEAN NOT NULL DEFAULT FALSE,     -- price by weight (groceries)
  has_variants BOOLEAN NOT NULL DEFAULT FALSE,
  image_url TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  UNIQUE (tenant_id, sku)
);
CREATE INDEX idx_products_tenant ON products(tenant_id) WHERE deleted_at IS NULL AND is_active = TRUE;
CREATE INDEX idx_products_barcode ON products(tenant_id, barcode) WHERE barcode IS NOT NULL;
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_search ON products USING gin (to_tsvector('english', name || ' ' || coalesce(description, '')));
```

### `product_variants`
For products like clothing (size × color).

```sql
CREATE TABLE product_variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  sku VARCHAR(50) NOT NULL,
  barcode VARCHAR(50),
  attributes JSONB NOT NULL,                        -- {"size": "L", "color": "blue"}
  cost_price DECIMAL(14, 4),
  sale_price DECIMAL(14, 4),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_variants_sku ON product_variants(product_id, sku);
```

### `product_batches`
For pharma and date-sensitive goods.

```sql
CREATE TABLE product_batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  batch_number VARCHAR(50) NOT NULL,
  manufactured_date DATE,
  expiry_date DATE,
  cost_price DECIMAL(14, 4),
  sale_price DECIMAL(14, 4),
  initial_quantity DECIMAL(14, 4) NOT NULL,
  current_quantity DECIMAL(14, 4) NOT NULL,
  branch_id UUID REFERENCES branches(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (product_id, batch_number, branch_id)
);
CREATE INDEX idx_batches_expiry ON product_batches(expiry_date) WHERE current_quantity > 0;
```

---

## Section 4 — Inventory

### `stock_levels`
Current stock per product per branch.

```sql
CREATE TABLE stock_levels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
  branch_id UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
  quantity DECIMAL(14, 4) NOT NULL DEFAULT 0,
  reserved_quantity DECIMAL(14, 4) NOT NULL DEFAULT 0,  -- held in carts/pending sales
  reorder_level DECIMAL(14, 4),                          -- per-branch override
  last_counted_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (product_id, variant_id, branch_id)
);
CREATE INDEX idx_stock_branch ON stock_levels(branch_id);
CREATE INDEX idx_stock_low ON stock_levels(tenant_id) WHERE quantity <= COALESCE(reorder_level, 0);
```

### `stock_movements`
Append-only ledger of every stock change. **Never updated, only inserted.**

```sql
CREATE TABLE stock_movements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  batch_id UUID REFERENCES product_batches(id),
  branch_id UUID NOT NULL REFERENCES branches(id),
  movement_type VARCHAR(30) NOT NULL,
  -- 'sale' | 'return' | 'purchase' | 'transfer_in' | 'transfer_out'
  -- 'adjustment_in' | 'adjustment_out' | 'damage' | 'expiry' | 'opening_balance'
  quantity DECIMAL(14, 4) NOT NULL,                  -- signed: positive = stock in, negative = stock out
  unit_cost DECIMAL(14, 4),
  reference_type VARCHAR(30),                        -- 'invoice' | 'return' | 'purchase_order' | 'adjustment'
  reference_id UUID,
  reason TEXT,
  performed_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_movements_product ON stock_movements(product_id, created_at DESC);
CREATE INDEX idx_movements_branch_date ON stock_movements(branch_id, created_at DESC);
CREATE INDEX idx_movements_reference ON stock_movements(reference_type, reference_id);
```

### `stock_transfers`
Movement of stock between branches with in-transit tracking.

```sql
CREATE TABLE stock_transfers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  transfer_number VARCHAR(20) NOT NULL,
  from_branch_id UUID NOT NULL REFERENCES branches(id),
  to_branch_id UUID NOT NULL REFERENCES branches(id),
  status VARCHAR(20) NOT NULL DEFAULT 'draft',     -- draft | dispatched | received | cancelled
  dispatched_at TIMESTAMPTZ,
  dispatched_by UUID REFERENCES users(id),
  received_at TIMESTAMPTZ,
  received_by UUID REFERENCES users(id),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, transfer_number)
);

CREATE TABLE stock_transfer_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  transfer_id UUID NOT NULL REFERENCES stock_transfers(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  quantity_dispatched DECIMAL(14, 4) NOT NULL,
  quantity_received DECIMAL(14, 4),
  variance DECIMAL(14, 4)
);
```

### `stock_audits`
Physical stock count cycles.

```sql
CREATE TABLE stock_audits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  branch_id UUID NOT NULL REFERENCES branches(id),
  audit_number VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'in_progress',  -- in_progress | finalized | cancelled
  started_at TIMESTAMPTZ NOT NULL,
  finalized_at TIMESTAMPTZ,
  performed_by UUID REFERENCES users(id),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE stock_audit_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_id UUID NOT NULL REFERENCES stock_audits(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  expected_quantity DECIMAL(14, 4) NOT NULL,
  counted_quantity DECIMAL(14, 4) NOT NULL,
  variance DECIMAL(14, 4) NOT NULL,
  variance_reason TEXT
);
```

---

## Section 5 — Suppliers & purchases

### `suppliers`
```sql
CREATE TABLE suppliers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  contact_person VARCHAR(255),
  ntn VARCHAR(20),
  strn VARCHAR(20),
  phone VARCHAR(20),
  email VARCHAR(255),
  address TEXT,
  payment_terms_days INT NOT NULL DEFAULT 0,
  opening_balance DECIMAL(14, 4) NOT NULL DEFAULT 0,
  current_balance DECIMAL(14, 4) NOT NULL DEFAULT 0,  -- positive = we owe them
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_suppliers_tenant ON suppliers(tenant_id) WHERE deleted_at IS NULL;
```

### `purchase_orders`
```sql
CREATE TABLE purchase_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  supplier_id UUID NOT NULL REFERENCES suppliers(id),
  branch_id UUID NOT NULL REFERENCES branches(id),
  po_number VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'draft',    -- draft | sent | partial | received | cancelled
  expected_delivery_date DATE,
  subtotal DECIMAL(14, 4) NOT NULL DEFAULT 0,
  tax_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  discount_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  shipping DECIMAL(14, 4) NOT NULL DEFAULT 0,
  grand_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  paid_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  notes TEXT,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, po_number)
);

CREATE TABLE purchase_order_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  po_id UUID NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  quantity_ordered DECIMAL(14, 4) NOT NULL,
  quantity_received DECIMAL(14, 4) NOT NULL DEFAULT 0,
  unit_cost DECIMAL(14, 4) NOT NULL,
  tax_rate DECIMAL(5, 2) NOT NULL DEFAULT 0,
  discount_pct DECIMAL(5, 2) NOT NULL DEFAULT 0,
  line_total DECIMAL(14, 4) NOT NULL
);
```

### `goods_receipts`
The actual receipt against a PO.

```sql
CREATE TABLE goods_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  po_id UUID REFERENCES purchase_orders(id),
  supplier_id UUID NOT NULL REFERENCES suppliers(id),
  branch_id UUID NOT NULL REFERENCES branches(id),
  grn_number VARCHAR(20) NOT NULL,
  supplier_invoice_number VARCHAR(50),
  receipt_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'received',
  subtotal DECIMAL(14, 4) NOT NULL DEFAULT 0,
  tax_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  grand_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  notes TEXT,
  received_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, grn_number)
);

CREATE TABLE goods_receipt_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  grn_id UUID NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
  po_item_id UUID REFERENCES purchase_order_items(id),
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  batch_id UUID REFERENCES product_batches(id),
  quantity DECIMAL(14, 4) NOT NULL,
  unit_cost DECIMAL(14, 4) NOT NULL,
  tax_rate DECIMAL(5, 2) NOT NULL DEFAULT 0,
  line_total DECIMAL(14, 4) NOT NULL
);
```

---

## Section 6 — Customers

### `customer_groups`
For tiered pricing.

```sql
CREATE TABLE customer_groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  default_discount_pct DECIMAL(5, 2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, name)
);
```

### `customers`
```sql
CREATE TABLE customers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  group_id UUID REFERENCES customer_groups(id),
  customer_code VARCHAR(20),                       -- optional internal code
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  email VARCHAR(255),
  cnic VARCHAR(15),
  ntn VARCHAR(20),                                 -- if business customer
  registration_type VARCHAR(20) NOT NULL DEFAULT 'unregistered',  -- 'registered' | 'unregistered'
  province VARCHAR(20),
  address TEXT,
  date_of_birth DATE,
  credit_limit DECIMAL(14, 4) NOT NULL DEFAULT 0,
  current_balance DECIMAL(14, 4) NOT NULL DEFAULT 0,  -- positive = customer owes us
  store_credit DECIMAL(14, 4) NOT NULL DEFAULT 0,
  loyalty_points INT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_customers_tenant ON customers(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_customers_phone ON customers(tenant_id, phone) WHERE phone IS NOT NULL;
CREATE INDEX idx_customers_search ON customers USING gin (to_tsvector('simple', name || ' ' || coalesce(phone, '') || ' ' || coalesce(cnic, '')));
```

### `customer_ledger`
Credit/debit history per customer (purchases, payments, returns, adjustments).

```sql
CREATE TABLE customer_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES customers(id),
  transaction_type VARCHAR(30) NOT NULL,           -- 'sale' | 'payment' | 'return' | 'adjustment' | 'opening'
  reference_type VARCHAR(30),
  reference_id UUID,
  debit DECIMAL(14, 4) NOT NULL DEFAULT 0,
  credit DECIMAL(14, 4) NOT NULL DEFAULT 0,
  running_balance DECIMAL(14, 4) NOT NULL,
  notes TEXT,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ledger_customer_date ON customer_ledger(customer_id, created_at DESC);
```

---

## Section 7 — Sales

### `invoices`
The sale.

```sql
CREATE TABLE invoices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  branch_id UUID NOT NULL REFERENCES branches(id),
  terminal_id UUID NOT NULL REFERENCES terminals(id),
  cashier_id UUID NOT NULL REFERENCES users(id),
  cash_session_id UUID REFERENCES cash_sessions(id),
  customer_id UUID REFERENCES customers(id),       -- NULL for walk-in
  
  -- Local invoice numbering (always present)
  local_invoice_number VARCHAR(40) NOT NULL,       -- e.g. "MAIN-T1-2025-0001234"
  
  -- FBR-side identifiers (NULL until validated)
  fbr_invoice_number VARCHAR(40),                  -- the IRN PRAL returns
  fbr_qr_payload TEXT,                             -- full QR encoded data
  fbr_submitted_at TIMESTAMPTZ,
  fbr_validated_at TIMESTAMPTZ,
  
  invoice_type VARCHAR(30) NOT NULL DEFAULT 'sale',  -- 'sale' | 'debit_note' | 'credit_note'
  invoice_date DATE NOT NULL,
  
  -- Buyer details snapshotted at sale time (PRAL JSON requirements)
  buyer_name VARCHAR(255),
  buyer_ntn_cnic VARCHAR(20),
  buyer_phone VARCHAR(20),
  buyer_address TEXT,
  buyer_province VARCHAR(20),
  buyer_registration_type VARCHAR(20) NOT NULL DEFAULT 'Unregistered',
  
  -- Money (excl. tax = subtotal, incl. tax = grand total)
  subtotal DECIMAL(14, 4) NOT NULL DEFAULT 0,
  discount_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  tax_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  further_tax_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  fed_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  withholding_tax_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  rounding_adjustment DECIMAL(14, 4) NOT NULL DEFAULT 0,
  grand_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  paid_total DECIMAL(14, 4) NOT NULL DEFAULT 0,
  change_given DECIMAL(14, 4) NOT NULL DEFAULT 0,
  
  -- Status
  status VARCHAR(40) NOT NULL DEFAULT 'pending_sync',
  -- pending_sync | submitted | valid | failed
  -- edited | partially_edited
  -- cancelled | partially_cancelled | partially_edited_and_cancelled
  -- finalized
  
  -- Lifecycle deadlines
  edit_deadline_at TIMESTAMPTZ,                    -- min(insertion + 72h, month_end)
  
  -- Reference for credit/debit notes
  reference_invoice_id UUID REFERENCES invoices(id),
  reason VARCHAR(50),
  reason_notes TEXT,
  
  -- Idempotency for sync
  client_uuid UUID NOT NULL UNIQUE,                -- generated on POS at sale time
  
  notes TEXT,
  is_held BOOLEAN NOT NULL DEFAULT FALSE,          -- "park sale" feature
  held_label VARCHAR(50),                          -- e.g. customer name on hold
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  UNIQUE (tenant_id, local_invoice_number),
  UNIQUE (fbr_invoice_number)
);
CREATE INDEX idx_invoices_tenant_date ON invoices(tenant_id, invoice_date DESC);
CREATE INDEX idx_invoices_branch_date ON invoices(branch_id, invoice_date DESC);
CREATE INDEX idx_invoices_status ON invoices(tenant_id, status) WHERE status IN ('pending_sync', 'submitted', 'failed');
CREATE INDEX idx_invoices_edit_deadline ON invoices(edit_deadline_at) WHERE status NOT IN ('finalized', 'cancelled');
CREATE INDEX idx_invoices_customer ON invoices(customer_id, invoice_date DESC);
CREATE INDEX idx_invoices_held ON invoices(tenant_id, branch_id) WHERE is_held = TRUE;
```

### `sale_items`
Line items.

```sql
CREATE TABLE sale_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  line_number INT NOT NULL,
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  batch_id UUID REFERENCES product_batches(id),
  
  -- Snapshot fields (price/cost at sale time, never updated)
  product_name VARCHAR(255) NOT NULL,
  product_sku VARCHAR(50) NOT NULL,
  hs_code VARCHAR(15),
  uom_code VARCHAR(20) NOT NULL,
  sale_type VARCHAR(50) NOT NULL DEFAULT 'Goods at standard rate (default)',
  
  quantity DECIMAL(14, 4) NOT NULL,
  unit_price DECIMAL(14, 4) NOT NULL,              -- excl. tax
  cost_price DECIMAL(14, 4),                       -- snapshot for profit calculation
  
  discount_pct DECIMAL(5, 2) NOT NULL DEFAULT 0,
  discount_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  
  tax_rate DECIMAL(5, 2) NOT NULL DEFAULT 0,
  tax_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  further_tax_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  fed_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  st_withheld_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  
  fixed_notified_value DECIMAL(14, 4),             -- retail price, if applicable
  sro_schedule_no VARCHAR(20),
  sro_item_serial_no VARCHAR(20),
  
  line_total DECIMAL(14, 4) NOT NULL,              -- final amount including tax
  
  -- Edit/cancel tracking (per PRAL rules)
  is_edited BOOLEAN NOT NULL DEFAULT FALSE,
  is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
  edited_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  edit_count INT NOT NULL DEFAULT 0,               -- max 1 per PRAL rules
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  UNIQUE (invoice_id, line_number)
);
CREATE INDEX idx_sale_items_invoice ON sale_items(invoice_id);
CREATE INDEX idx_sale_items_product_date ON sale_items(product_id, created_at DESC);
```

### `sale_item_history`
For viewing pre-edit values (per PRAL spec, original details must remain viewable).

```sql
CREATE TABLE sale_item_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sale_item_id UUID NOT NULL REFERENCES sale_items(id) ON DELETE CASCADE,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  changed_by UUID REFERENCES users(id),
  change_type VARCHAR(20) NOT NULL,                -- 'edit' | 'cancel'
  previous_data JSONB NOT NULL                     -- full snapshot of fields before change
);
```

### `payments`
A single payment can fund part of one invoice. An invoice can have multiple payments (split tender).

```sql
CREATE TABLE payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  invoice_id UUID REFERENCES invoices(id),         -- NULL for standalone customer payments
  customer_id UUID REFERENCES customers(id),
  
  payment_method VARCHAR(30) NOT NULL,
  -- 'cash' | 'card_credit' | 'card_debit'
  -- 'easypaisa' | 'jazzcash' | 'raast'
  -- 'bank_transfer' | 'store_credit' | 'cheque'
  
  amount DECIMAL(14, 4) NOT NULL,
  
  -- Method-specific fields
  card_last4 VARCHAR(4),
  card_terminal_id VARCHAR(50),                    -- merchant POS terminal ID
  card_auth_code VARCHAR(20),
  card_rrn VARCHAR(50),                            -- retrieval reference number
  
  wallet_provider VARCHAR(20),                     -- 'easypaisa' | 'jazzcash'
  wallet_phone VARCHAR(20),
  wallet_transaction_id VARCHAR(100),
  
  bank_name VARCHAR(50),
  bank_account_last4 VARCHAR(4),
  bank_reference VARCHAR(100),
  
  raast_iban VARCHAR(34),
  raast_transaction_id VARCHAR(100),
  
  cheque_number VARCHAR(50),
  cheque_date DATE,
  cheque_status VARCHAR(20),                       -- 'pending' | 'cleared' | 'bounced'
  
  status VARCHAR(20) NOT NULL DEFAULT 'completed', -- 'pending' | 'completed' | 'failed' | 'refunded'
  
  received_by UUID REFERENCES users(id),
  notes TEXT,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payments_invoice ON payments(invoice_id);
CREATE INDEX idx_payments_customer_date ON payments(customer_id, created_at DESC);
CREATE INDEX idx_payments_method_date ON payments(tenant_id, payment_method, created_at DESC);
```

### `held_sales` (concept folds into `invoices.is_held`, no separate table needed)

### `discounts` and `promotions`
```sql
CREATE TABLE discounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  discount_type VARCHAR(20) NOT NULL,              -- 'percentage' | 'fixed' | 'buy_x_get_y'
  value DECIMAL(14, 4) NOT NULL,
  min_purchase_amount DECIMAL(14, 4),
  applies_to VARCHAR(20) NOT NULL,                 -- 'all' | 'category' | 'product' | 'customer_group'
  applies_to_ids UUID[],
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ,
  max_uses INT,
  uses_count INT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Section 8 — Returns

### `returns`
```sql
CREATE TABLE returns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  branch_id UUID NOT NULL REFERENCES branches(id),
  terminal_id UUID NOT NULL REFERENCES terminals(id),
  cashier_id UUID NOT NULL REFERENCES users(id),
  customer_id UUID REFERENCES customers(id),
  original_invoice_id UUID REFERENCES invoices(id),
  
  return_number VARCHAR(40) NOT NULL,
  fbr_credit_note_number VARCHAR(40),              -- if FBR-submitted as credit note
  return_date DATE NOT NULL,
  
  reason VARCHAR(50) NOT NULL,                     -- 'damaged' | 'wrong_item' | 'customer_changed_mind' | 'expired' | 'other'
  reason_notes TEXT,
  
  refund_method VARCHAR(30) NOT NULL,              -- 'cash' | 'store_credit' | 'card_reversal' | 'wallet_reversal' | 'bank_transfer'
  refund_amount DECIMAL(14, 4) NOT NULL,
  
  status VARCHAR(20) NOT NULL DEFAULT 'completed',  -- 'pending' | 'completed' | 'cancelled'
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  UNIQUE (tenant_id, return_number)
);
CREATE INDEX idx_returns_tenant_date ON returns(tenant_id, return_date DESC);

CREATE TABLE return_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  return_id UUID NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
  original_sale_item_id UUID REFERENCES sale_items(id),
  product_id UUID NOT NULL REFERENCES products(id),
  variant_id UUID REFERENCES product_variants(id),
  quantity DECIMAL(14, 4) NOT NULL,
  unit_price DECIMAL(14, 4) NOT NULL,
  tax_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  line_total DECIMAL(14, 4) NOT NULL,
  restocked BOOLEAN NOT NULL DEFAULT TRUE          -- if FALSE: damaged, written off
);
```

---

## Section 9 — FBR / Compliance

### `fbr_tokens`
Per-tenant sandbox and production tokens.

```sql
CREATE TABLE fbr_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  environment VARCHAR(20) NOT NULL,                -- 'sandbox' | 'production'
  licensed_integrator VARCHAR(50) NOT NULL DEFAULT 'PRAL',
  token_encrypted TEXT NOT NULL,                   -- encrypted with app-level key
  api_endpoint TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  activated_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, environment)
);
```

### `fbr_submissions`
Every API call to PRAL. Append-only.

```sql
CREATE TABLE fbr_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  invoice_id UUID REFERENCES invoices(id),
  return_id UUID REFERENCES returns(id),
  environment VARCHAR(20) NOT NULL,
  endpoint VARCHAR(100) NOT NULL,                  -- 'postinvoicedata' | 'validateinvoicedata' | 'cancelinvoice' | 'editinvoice'
  
  request_payload JSONB NOT NULL,
  response_payload JSONB,
  
  http_status INT,
  status_code VARCHAR(20),                         -- PRAL's "00" | "01"
  fbr_invoice_number VARCHAR(40),
  
  attempt_number INT NOT NULL DEFAULT 1,
  duration_ms INT,
  error_message TEXT,
  
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fbr_submissions_invoice ON fbr_submissions(invoice_id, submitted_at DESC);
CREATE INDEX idx_fbr_submissions_failed ON fbr_submissions(tenant_id, submitted_at DESC) WHERE status_code != '00';
```

### `fbr_scenario_tests`
Tracks sandbox scenario completion (SN001…SN015+).

```sql
CREATE TABLE fbr_scenario_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  scenario_code VARCHAR(10) NOT NULL,              -- 'SN001'
  scenario_description TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',   -- 'pending' | 'submitted' | 'success' | 'failed'
  fbr_invoice_number VARCHAR(40),
  last_attempt_at TIMESTAMPTZ,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, scenario_code)
);
```

### `fbr_cancel_budget`
The 10% monthly cap.

```sql
CREATE TABLE fbr_cancel_budget (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  month_start DATE NOT NULL,                       -- first of the month
  previous_month_sales DECIMAL(14, 4) NOT NULL,    -- baseline for 10%
  budget_amount DECIMAL(14, 4) NOT NULL,           -- = previous_month_sales * 0.10
  consumed_amount DECIMAL(14, 4) NOT NULL DEFAULT 0,
  remaining_amount DECIMAL(14, 4) NOT NULL,
  last_recalculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, month_start)
);

CREATE TABLE fbr_cancel_budget_consumption (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  budget_id UUID NOT NULL REFERENCES fbr_cancel_budget(id),
  invoice_id UUID NOT NULL REFERENCES invoices(id),
  consumption_type VARCHAR(20) NOT NULL,           -- 'edit' | 'cancel'
  amount DECIMAL(14, 4) NOT NULL,
  consumed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  consumed_by UUID REFERENCES users(id)
);
CREATE INDEX idx_consumption_budget ON fbr_cancel_budget_consumption(budget_id);
```

### `fbr_ip_whitelist`
The static IPs we declare to PRAL on behalf of tenants (or global to our infra).

```sql
CREATE TABLE fbr_ip_whitelist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,  -- NULL means global infra IP
  ip_address INET NOT NULL,
  hosting_provider VARCHAR(100),
  hosting_country VARCHAR(50),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',   -- 'pending' | 'approved' | 'rejected'
  approved_at TIMESTAMPTZ,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Section 10 — Sync engine

### `sync_queue`
Outbound queue from POS terminal to server (lives on the terminal in SQLite, mirrored in Postgres for analytics).

```sql
-- Postgres-side: server-received items only, for monitoring
CREATE TABLE sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  terminal_id UUID NOT NULL REFERENCES terminals(id),
  client_uuid UUID NOT NULL,                       -- idempotency key from terminal
  entity_type VARCHAR(30) NOT NULL,                -- 'invoice' | 'return' | 'customer' | 'stock_adjustment'
  entity_id UUID NOT NULL,
  action VARCHAR(20) NOT NULL,                     -- 'create' | 'update'
  
  payload JSONB NOT NULL,                          -- the body the terminal sent
  
  status VARCHAR(20) NOT NULL DEFAULT 'received',  -- 'received' | 'processed' | 'failed' | 'duplicate'
  error_message TEXT,
  
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  
  UNIQUE (client_uuid)                             -- idempotency enforcement
);
CREATE INDEX idx_sync_log_terminal ON sync_log(terminal_id, received_at DESC);
CREATE INDEX idx_sync_log_failed ON sync_log(tenant_id) WHERE status = 'failed';
```

The terminal-side SQLite mirror (in `pos-terminal/electron/db/schema.sql`):

```sql
-- SQLite on POS terminal
CREATE TABLE outbound_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_uuid TEXT NOT NULL UNIQUE,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  payload TEXT NOT NULL,                           -- JSON string
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,                   -- ISO datetime
  last_error TEXT,
  status TEXT NOT NULL DEFAULT 'pending',          -- pending | sent | failed | cancelled
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at TEXT
);
CREATE INDEX idx_queue_pending ON outbound_queue(next_attempt_at) WHERE status = 'pending';
```

---

## Section 11 — Audit & settings

### `audit_log`
Append-only, immutable, every meaningful change.

```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,  -- keep audit even if tenant deleted
  user_id UUID REFERENCES users(id),
  
  entity_type VARCHAR(50) NOT NULL,                -- 'invoice' | 'product' | 'price' | 'user' | 'permission'
  entity_id UUID,
  action VARCHAR(50) NOT NULL,                     -- 'create' | 'update' | 'delete' | 'cancel' | 'login' | 'permission_change'
  
  before_data JSONB,
  after_data JSONB,
  changes JSONB,                                   -- { "field": ["old", "new"], ... }
  
  ip_address INET,
  user_agent TEXT,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_tenant_date ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_user_date ON audit_log(user_id, created_at DESC);

-- Make audit_log truly append-only at the database level
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
```

### `tenant_settings`
Per-tenant configurable behaviors.

```sql
CREATE TABLE tenant_settings (
  tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  
  -- Receipt
  receipt_paper_width INT NOT NULL DEFAULT 80,     -- 58 | 80
  receipt_show_logo BOOLEAN NOT NULL DEFAULT TRUE,
  receipt_header TEXT,
  receipt_footer TEXT,
  receipt_show_qr BOOLEAN NOT NULL DEFAULT TRUE,
  receipt_show_buyer BOOLEAN NOT NULL DEFAULT TRUE,
  receipt_language VARCHAR(10) NOT NULL DEFAULT 'en',
  
  -- Cashier
  require_customer_for_credit BOOLEAN NOT NULL DEFAULT TRUE,
  allow_negative_stock BOOLEAN NOT NULL DEFAULT FALSE,
  manager_pin_for_void BOOLEAN NOT NULL DEFAULT TRUE,
  manager_pin_for_discount_above_pct DECIMAL(5, 2) DEFAULT 10,
  default_low_stock_threshold INT NOT NULL DEFAULT 5,
  
  -- FBR
  auto_submit_to_fbr BOOLEAN NOT NULL DEFAULT TRUE,
  cancel_budget_alert_threshold_pct INT NOT NULL DEFAULT 80,
  
  -- Sync
  sync_interval_seconds INT NOT NULL DEFAULT 30,
  
  -- Notifications
  daily_report_email BOOLEAN NOT NULL DEFAULT TRUE,
  daily_report_time TIME NOT NULL DEFAULT '23:30',
  low_stock_alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  
  -- Tax
  tax_inclusive_pricing BOOLEAN NOT NULL DEFAULT FALSE,
  default_tax_rate_id UUID REFERENCES tax_rates(id),
  
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `notifications`
In-app and emitted notifications.

```sql
CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),               -- NULL = broadcast to all
  notification_type VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  severity VARCHAR(20) NOT NULL DEFAULT 'info',    -- info | warning | danger | success
  data JSONB,
  read_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id) WHERE read_at IS NULL;
```

### `licenses`
Activation keys to deter pirated copies.

```sql
CREATE TABLE licenses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  license_key VARCHAR(100) NOT NULL UNIQUE,
  max_terminals INT NOT NULL DEFAULT 1,
  max_branches INT NOT NULL DEFAULT 1,
  features TEXT[],                                 -- ['fbr', 'multi_branch', 'advanced_reports']
  issued_at TIMESTAMPTZ NOT NULL,
  valid_until TIMESTAMPTZ NOT NULL,
  last_heartbeat_at TIMESTAMPTZ,
  is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
  revocation_reason TEXT
);
```

---

## Section 12 — Indexing summary & performance notes

**Hot-path queries and their supporting indexes:**

1. *Cashier scans barcode* → `idx_products_barcode (tenant_id, barcode)`
2. *Cashier searches product* → `idx_products_search (gin tsvector)` — full-text
3. *Today's sales for terminal* → `idx_invoices_branch_date (branch_id, invoice_date DESC)`
4. *Pending sync queue on terminal* → SQLite `idx_queue_pending`
5. *Failed FBR submissions for admin alert* → `idx_fbr_submissions_failed`
6. *Stock-low alert daily job* → `idx_stock_low (partial)`
7. *Customer lookup by phone* → `idx_customers_phone`
8. *Edit-window expiry reminder job* → `idx_invoices_edit_deadline (partial)`
9. *Per-cashier daily summary* → no extra index — predicate hits `idx_invoices_branch_date` and small daily set

**Postgres tuning starting point** (8 GB RAM VPS):

```
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 16MB
maintenance_work_mem = 256MB
random_page_cost = 1.1   -- SSD
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
```

---

## Section 13 — Migration order

Safe order to run migrations from scratch:

1. `users`, `tenants`, `tenant_memberships`
2. Lookup tables: `units_of_measure`, `hs_codes` (seed data)
3. `branches`, `terminals`
4. `categories`, `tax_rates`, `products`, `product_variants`, `product_batches`
5. `stock_levels`, `stock_movements`, `stock_transfers` + items, `stock_audits` + items
6. `suppliers`, `purchase_orders` + items, `goods_receipts` + items
7. `customer_groups`, `customers`, `customer_ledger`
8. `cash_sessions`
9. `invoices`, `sale_items`, `sale_item_history`, `payments`
10. `returns`, `return_items`
11. `discounts`
12. `fbr_tokens`, `fbr_submissions`, `fbr_scenario_tests`, `fbr_cancel_budget`, `fbr_cancel_budget_consumption`, `fbr_ip_whitelist`
13. `sync_log`
14. `audit_log`
15. `tenant_settings`, `notifications`, `licenses`

Always create extension `pgcrypto` first for `gen_random_uuid()`.

---

## Section 14 — Things that look like tables but aren't

Don't make these tables. They're either folded into other tables or computed on demand:

- *Inventory by category* — view, not table.
- *Sales by hour/day/week* — aggregation in Celery + cached in Redis, not a denormalized table.
- *Top customers* — query over `invoices` joined with `customers`; cache in Redis.
- *"Held sales"* — flag on `invoices` (`is_held`).
- *"Drafts"* — POS terminal SQLite only; the cloud only ever sees finalized sales.

---

*Schema version: 1.0. Track changes via Django migrations under `backend/apps/*/migrations/`. Never edit a migration after it's been applied to production — write a new one.*
