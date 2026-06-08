/**
 * Build a cart-line input from a product row, attaching the FEFO batch when the
 * product is batch-tracked (pharmacy / date-sensitive goods).
 *
 * For a batch-tracked product we look up the nearest-expiry in-stock batch
 * locally (offline-safe — reads the terminal's product_batches mirror) and
 * stamp batch_id/batch_number/expiry_date onto the line so checkout draws stock
 * from that batch. Non-batch-tracked products (the common case) are returned
 * unchanged.
 *
 * Returns the line input plus a `warning` when a batch-tracked product has no
 * in-stock batch, so the caller can surface it to the cashier (we still let the
 * sale proceed unbatched rather than blocking the counter).
 */

import type { PosProductSqliteRow } from "../../../electron/preload";
import type { CartLine } from "@/stores/sale";

export type CartLineInput = Omit<CartLine, "id" | "quantity"> & { quantity?: string };

export async function buildCartLineFromProduct(
  p: PosProductSqliteRow,
  opts: { branchId?: string | null; quantity?: string } = {},
): Promise<{ line: CartLineInput; warning?: string }> {
  const base: CartLineInput = {
    product_id: p.id,
    product_name: p.name,
    product_sku: p.sku,
    uom_code: p.uom_code,
    hs_code: (p as { hs_code?: string | null }).hs_code ?? null,
    quantity: opts.quantity ?? "1",
    unit_price: p.sale_price,
    discount_pct: "0",
    discount_amount: "0",
    tax_rate: p.is_taxable ? "18" : "0",
    is_taxable: !!p.is_taxable,
  };

  if (!p.is_batch_tracked) {
    return { line: base };
  }

  // Batch-tracked: pick the soonest-expiry in-stock batch (FEFO).
  try {
    const batch = await window.api.catalog.nearestBatch(p.id, opts.branchId ?? null);
    if (!batch) {
      return {
        line: base,
        warning: `No in-stock batch for ${p.name}. Sold without a batch — restock soon.`,
      };
    }
    const expired = batch.expiry_date
      ? new Date(batch.expiry_date + "T00:00:00") < new Date(new Date().toDateString())
      : false;
    return {
      line: {
        ...base,
        batch_id: batch.id,
        batch_number: batch.batch_number,
        expiry_date: batch.expiry_date,
      },
      warning: expired
        ? `Batch ${batch.batch_number} of ${p.name} is EXPIRED (${batch.expiry_date}).`
        : undefined,
    };
  } catch {
    // Batch lookup failed — don't block the sale; sell unbatched.
    return { line: base };
  }
}
