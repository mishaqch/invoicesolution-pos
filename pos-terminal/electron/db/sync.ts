/**
 * Catalog sync — pulls products + categories + stock levels from the server
 * and upserts them into local SQLite.
 *
 * Phase 1: simple last-updated-at polling. Phase 3 will replace this with the
 * real bidirectional sync engine.
 */

import { getDb } from "./client";

interface PosProductRow {
  id: string;
  category: string | null;
  sku: string;
  barcode: string | null;
  name: string;
  name_ur: string;
  uom: string;
  tax_rate: string | null;
  tax_rate_value: string | null;
  hs_code: string | null;
  is_taxable: boolean;
  sale_price: string;
  retail_price: string | null;
  min_sale_price: string | null;
  max_discount_pct: string | null;
  is_third_schedule: boolean;
  sale_type?: string;
  is_weighable: boolean;
  is_batch_tracked: boolean;
  image_url: string;
  is_active: boolean;
  updated_at: string;
  deleted_at: string | null;
}

interface PosBatchRow {
  id: string;
  product: string;
  batch_number: string;
  expiry_date: string | null;
  current_quantity: string;
  branch: string | null;
}

export interface LocalBatch {
  id: string;
  product_id: string;
  batch_number: string;
  expiry_date: string | null;
  current_quantity: string;
  branch_id: string | null;
}

interface CategoryRow {
  id: string;
  parent: string | null;
  name: string;
  name_ur: string;
  display_order: number;
  color: string | null;
  icon: string | null;
  is_active: boolean;
  updated_at: string;
}

export async function syncCatalog(opts: {
  apiBase: string;
  accessToken: string;
  /** The logged-in tenant's id. If it differs from the tenant the local
   *  catalog was last synced for, we WIPE the local catalog and do a clean full
   *  pull — otherwise an incremental (?since=) sync only ADDS rows, so a
   *  terminal that previously synced a grocery tenant would keep showing those
   *  products after logging into a restaurant tenant. */
  tenantId?: string | null;
  /** Force a wipe + full re-pull even if the tenant hasn't changed (the
   *  "Reset catalog" escape hatch). */
  force?: boolean;
}): Promise<{ products: number; categories: number; batches: number }> {
  const db = getDb();

  // Detect a tenant switch (or a first-ever sync) and reset the local catalog.
  const lastTenant = (db
    .prepare("SELECT value FROM kv_meta WHERE key = 'catalog.tenant_id'")
    .get() as { value: string } | undefined)?.value ?? null;
  const tenantChanged = opts.force || (!!opts.tenantId && lastTenant !== opts.tenantId);
  if (tenantChanged) {
    const wipe = db.transaction(() => {
      db.prepare("DELETE FROM products").run();
      db.prepare("DELETE FROM products_fts").run();
      db.prepare("DELETE FROM categories").run();
      db.prepare("DELETE FROM product_batches").run();
      db.prepare("DELETE FROM stock_levels").run();
      db.prepare("DELETE FROM meta_sync WHERE entity = 'products'").run();
      db.prepare(
        "INSERT INTO kv_meta(key, value, updated_at) VALUES ('catalog.tenant_id', ?, CURRENT_TIMESTAMP) " +
          "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
      ).run(opts.tenantId);
    });
    wipe();
  }

  // After a wipe, `since` is gone → a full pull. Normal runs stay incremental.
  const since = tenantChanged ? undefined : (db
    .prepare("SELECT last_synced_at FROM meta_sync WHERE entity = 'products'")
    .get() as { last_synced_at: string } | undefined)?.last_synced_at;

  const url = new URL(`${opts.apiBase}/api/catalog/sync/`);
  if (since) url.searchParams.set("since", since);

  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${opts.accessToken}` },
  });
  if (!resp.ok) throw new Error(`sync failed: ${resp.status}`);

  const data = (await resp.json()) as {
    products: PosProductRow[];
    categories: CategoryRow[];
    batches?: PosBatchRow[];
    batches_full_snapshot?: boolean;
  };

  const upsertProduct = db.prepare(`
    INSERT INTO products (
      id, category_id, sku, barcode, name, name_ur, uom_code, tax_rate_id, tax_rate_value,
      hs_code, is_taxable, sale_price, retail_price, min_sale_price, max_discount_pct,
      is_third_schedule, sale_type, is_weighable, is_batch_tracked, image_url, is_active, updated_at, deleted_at
    ) VALUES (
      @id, @category, @sku, @barcode, @name, @name_ur, @uom, @tax_rate, @tax_rate_value,
      @hs_code, @is_taxable, @sale_price, @retail_price, @min_sale_price, @max_discount_pct,
      @is_third_schedule, @sale_type, @is_weighable, @is_batch_tracked, @image_url, @is_active, @updated_at, @deleted_at
    )
    ON CONFLICT(id) DO UPDATE SET
      category_id=excluded.category_id, sku=excluded.sku, barcode=excluded.barcode,
      name=excluded.name, name_ur=excluded.name_ur, uom_code=excluded.uom_code,
      tax_rate_id=excluded.tax_rate_id, tax_rate_value=excluded.tax_rate_value,
      hs_code=excluded.hs_code, is_taxable=excluded.is_taxable,
      sale_price=excluded.sale_price, retail_price=excluded.retail_price,
      min_sale_price=excluded.min_sale_price, max_discount_pct=excluded.max_discount_pct,
      is_third_schedule=excluded.is_third_schedule, sale_type=excluded.sale_type,
      is_weighable=excluded.is_weighable, is_batch_tracked=excluded.is_batch_tracked,
      image_url=excluded.image_url,
      is_active=excluded.is_active, updated_at=excluded.updated_at,
      deleted_at=excluded.deleted_at
  `);

  const insertBatch = db.prepare(`
    INSERT INTO product_batches (id, product_id, batch_number, expiry_date, current_quantity, branch_id)
    VALUES (@id, @product_id, @batch_number, @expiry_date, @current_quantity, @branch_id)
  `);

  const deleteFts = db.prepare(`DELETE FROM products_fts WHERE id = ?`);
  const insertFts = db.prepare(
    `INSERT INTO products_fts (id, name, name_ur, sku, barcode) VALUES (?, ?, ?, ?, ?)`,
  );

  const upsertCategory = db.prepare(`
    INSERT INTO categories (id, parent_id, name, name_ur, display_order, color, icon, is_active, updated_at)
    VALUES (@id, @parent, @name, @name_ur, @display_order, @color, @icon, @is_active, @updated_at)
    ON CONFLICT(id) DO UPDATE SET
      parent_id=excluded.parent_id, name=excluded.name, name_ur=excluded.name_ur,
      display_order=excluded.display_order, color=excluded.color, icon=excluded.icon,
      is_active=excluded.is_active, updated_at=excluded.updated_at
  `);

  const tx = db.transaction(() => {
    for (const p of data.products) {
      upsertProduct.run({
        ...p,
        hs_code: (p as { hs_code?: string | null }).hs_code ?? null,
        tax_rate_value: (p as { tax_rate_value?: string | null }).tax_rate_value ?? null,
        is_taxable: p.is_taxable ? 1 : 0,
        is_third_schedule: (p as { is_third_schedule?: boolean }).is_third_schedule ? 1 : 0,
        sale_type: (p as { sale_type?: string }).sale_type ?? "Goods at standard rate (default)",
        is_weighable: p.is_weighable ? 1 : 0,
        is_batch_tracked: (p as { is_batch_tracked?: boolean }).is_batch_tracked ? 1 : 0,
        is_active: p.is_active ? 1 : 0,
      });
      // Maintain FTS index manually (we used content='' above).
      deleteFts.run(p.id);
      if (!p.deleted_at) {
        insertFts.run(p.id, p.name, p.name_ur ?? "", p.sku, p.barcode ?? "");
      }
    }
    for (const c of data.categories) {
      upsertCategory.run({
        ...c,
        display_order: c.display_order ?? 0,
        is_active: c.is_active ? 1 : 0,
      });
    }

    // Batches arrive as a FULL snapshot (the server can't incrementally express
    // current_quantity decrements). Replace the local table wholesale so a sold-
    // out / removed batch disappears. Only when the server actually sent the set.
    if (data.batches_full_snapshot && Array.isArray(data.batches)) {
      db.prepare(`DELETE FROM product_batches`).run();
      for (const b of data.batches) {
        insertBatch.run({
          id: b.id,
          product_id: b.product,
          batch_number: b.batch_number,
          expiry_date: b.expiry_date ?? null,
          current_quantity: b.current_quantity,
          branch_id: b.branch ?? null,
        });
      }
    }

    db.prepare(`
      INSERT INTO meta_sync (entity, last_synced_at) VALUES ('products', CURRENT_TIMESTAMP)
      ON CONFLICT(entity) DO UPDATE SET last_synced_at=CURRENT_TIMESTAMP
    `).run();

    // Record which tenant this catalog belongs to (so a future login as a
    // different tenant triggers the wipe above). Stamped on every successful
    // sync, covering the first-ever sync where no marker existed yet.
    if (opts.tenantId) {
      db.prepare(
        "INSERT INTO kv_meta(key, value, updated_at) VALUES ('catalog.tenant_id', ?, CURRENT_TIMESTAMP) " +
          "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
      ).run(opts.tenantId);
    }
  });
  tx();

  return {
    products: data.products.length,
    categories: data.categories.length,
    batches: data.batches?.length ?? 0,
  };
}

/**
 * FEFO batch pick for a product: the soonest-expiry batch that still has stock.
 * Used at sale time for batch-tracked products. Returns null when the product
 * has no in-stock batches (caller decides whether to block or sell unbatched).
 * Batches with no expiry sort last (NULLs last) so dated stock clears first.
 */
export function nearestExpiryBatch(productId: string, branchId?: string | null): LocalBatch | null {
  const db = getDb();
  const params: (string | number)[] = [productId];
  let branchClause = "";
  if (branchId) {
    branchClause = " AND (branch_id = ? OR branch_id IS NULL)";
    params.push(branchId);
  }
  const row = db
    .prepare(
      `SELECT id, product_id, batch_number, expiry_date, current_quantity, branch_id
       FROM product_batches
       WHERE product_id = ? AND CAST(current_quantity AS REAL) > 0${branchClause}
       ORDER BY (expiry_date IS NULL), expiry_date ASC
       LIMIT 1`,
    )
    .get(...params) as LocalBatch | undefined;
  return row ?? null;
}

/** All in-stock batches for a product, soonest-expiry first (FEFO order). */
export function batchesForProduct(productId: string, branchId?: string | null): LocalBatch[] {
  const db = getDb();
  const params: (string | number)[] = [productId];
  let branchClause = "";
  if (branchId) {
    branchClause = " AND (branch_id = ? OR branch_id IS NULL)";
    params.push(branchId);
  }
  return db
    .prepare(
      `SELECT id, product_id, batch_number, expiry_date, current_quantity, branch_id
       FROM product_batches
       WHERE product_id = ? AND CAST(current_quantity AS REAL) > 0${branchClause}
       ORDER BY (expiry_date IS NULL), expiry_date ASC`,
    )
    .all(...params) as LocalBatch[];
}

// Room products (SKU 'ROOM-…') are booked via the Stays / Rooms (Open Stay)
// flow, NOT sold as cart items on the sale page — exclude them from the product
// grid's search + default list so a cashier can't ring one up directly.
const _NOT_ROOM = "p.sku NOT LIKE 'ROOM%'";

export function searchProducts(query: string, limit = 50): PosProductRow[] {
  const db = getDb();
  if (!query.trim()) {
    return db
      .prepare(
        `SELECT * FROM products p WHERE p.deleted_at IS NULL AND p.is_active = 1
           AND ${_NOT_ROOM}
         ORDER BY p.name LIMIT ?`,
      )
      .all(limit) as PosProductRow[];
  }
  // FTS5 prefix search — append * for prefix matches.
  const ftsTerm = query
    .trim()
    .split(/\s+/)
    .map((t) => `${t.replace(/["']/g, "")}*`)
    .join(" ");
  return db
    .prepare(
      `SELECT p.* FROM products p
       JOIN products_fts f ON f.id = p.id
       WHERE f.products_fts MATCH ?
         AND p.deleted_at IS NULL AND p.is_active = 1
         AND ${_NOT_ROOM}
       LIMIT ?`,
    )
    .all(ftsTerm, limit) as PosProductRow[];
}

/**
 * Exact barcode lookup for the hardware scanner path. A USB scanner emits the
 * full code then Enter, so we want a deterministic single-row match, not the
 * fuzzy FTS search used for manual typing. Uses idx_products_barcode. Returns
 * null when nothing matches so the caller can beep/toast "unknown barcode".
 */
export function productByBarcode(barcode: string): PosProductRow | null {
  const code = barcode.trim();
  if (!code) return null;
  const row = getDb()
    .prepare(
      `SELECT * FROM products
       WHERE barcode = ? AND deleted_at IS NULL AND is_active = 1
       LIMIT 1`,
    )
    .get(code) as PosProductRow | undefined;
  return row ?? null;
}

export function listProducts(limit = 100): PosProductRow[] {
  return getDb()
    .prepare(
      `SELECT * FROM products WHERE deleted_at IS NULL AND is_active = 1
       ORDER BY name LIMIT ?`,
    )
    .all(limit) as PosProductRow[];
}

export function productsCount(): number {
  const row = getDb()
    .prepare("SELECT COUNT(*) AS n FROM products WHERE deleted_at IS NULL AND is_active = 1")
    .get() as { n: number };
  return row.n;
}

export interface PosCategoryRow {
  id: string;
  name: string;
  display_order: number;
  color: string | null;
  icon: string | null;
}

/** Categories that actually have at least one sellable product, ordered by
 *  display_order then name. Drives the till's category quick-filter chips
 *  (e.g. "Rooms" pinned first for the resort). */
export function listCategories(): PosCategoryRow[] {
  return getDb()
    .prepare(
      `SELECT c.id, c.name, c.display_order, c.color, c.icon
         FROM categories c
        WHERE c.is_active = 1
          AND EXISTS (
            SELECT 1 FROM products p
             WHERE p.category_id = c.id AND p.deleted_at IS NULL AND p.is_active = 1
          )
        ORDER BY c.display_order, c.name`,
    )
    .all() as PosCategoryRow[];
}

/** Products in one category, name-ordered. Backs the category chip tap. */
export function listProductsByCategory(categoryId: string, limit = 200): PosProductRow[] {
  return getDb()
    .prepare(
      `SELECT * FROM products
        WHERE category_id = ? AND deleted_at IS NULL AND is_active = 1
        ORDER BY name LIMIT ?`,
    )
    .all(categoryId, limit) as PosProductRow[];
}
