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
  is_taxable: boolean;
  sale_price: string;
  retail_price: string | null;
  min_sale_price: string | null;
  max_discount_pct: string | null;
  is_weighable: boolean;
  image_url: string;
  is_active: boolean;
  updated_at: string;
  deleted_at: string | null;
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
}): Promise<{ products: number; categories: number }> {
  const db = getDb();

  const since = (db
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
  };

  const upsertProduct = db.prepare(`
    INSERT INTO products (
      id, category_id, sku, barcode, name, name_ur, uom_code, tax_rate_id,
      is_taxable, sale_price, retail_price, min_sale_price, max_discount_pct,
      is_weighable, image_url, is_active, updated_at, deleted_at
    ) VALUES (
      @id, @category, @sku, @barcode, @name, @name_ur, @uom, @tax_rate,
      @is_taxable, @sale_price, @retail_price, @min_sale_price, @max_discount_pct,
      @is_weighable, @image_url, @is_active, @updated_at, @deleted_at
    )
    ON CONFLICT(id) DO UPDATE SET
      category_id=excluded.category_id, sku=excluded.sku, barcode=excluded.barcode,
      name=excluded.name, name_ur=excluded.name_ur, uom_code=excluded.uom_code,
      tax_rate_id=excluded.tax_rate_id, is_taxable=excluded.is_taxable,
      sale_price=excluded.sale_price, retail_price=excluded.retail_price,
      min_sale_price=excluded.min_sale_price, max_discount_pct=excluded.max_discount_pct,
      is_weighable=excluded.is_weighable, image_url=excluded.image_url,
      is_active=excluded.is_active, updated_at=excluded.updated_at,
      deleted_at=excluded.deleted_at
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
        is_taxable: p.is_taxable ? 1 : 0,
        is_weighable: p.is_weighable ? 1 : 0,
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

    db.prepare(`
      INSERT INTO meta_sync (entity, last_synced_at) VALUES ('products', CURRENT_TIMESTAMP)
      ON CONFLICT(entity) DO UPDATE SET last_synced_at=CURRENT_TIMESTAMP
    `).run();
  });
  tx();

  return { products: data.products.length, categories: data.categories.length };
}

export function searchProducts(query: string, limit = 50): PosProductRow[] {
  const db = getDb();
  if (!query.trim()) {
    return db
      .prepare(
        `SELECT * FROM products WHERE deleted_at IS NULL AND is_active = 1
         ORDER BY name LIMIT ?`,
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
