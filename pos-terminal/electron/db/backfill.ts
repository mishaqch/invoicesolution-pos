/**
 * One-time recovery of PAID sales that were never queued for sync.
 *
 * Cause (fixed in persistInvoice): a restaurant order reuses ONE client_uuid
 * for its whole life. It is persisted HELD when fired to the kitchen, then
 * persisted again at Charge. The second call hit the idempotency early-return
 * and exited BEFORE the enqueue block, so the paid invoice was never put on
 * outbound_queue. /api/sync/invoices/ was never called even once -- the sale
 * only ever reached the server as a held open order, which was then voided.
 *
 * persistInvoice now finalizes + enqueues on that second call, but only for
 * sales charged AFTER the update. Anything charged before it is already past
 * that code path, so this sweep re-queues it.
 *
 * Safety:
 *   - Only rows that HAVE a completed payment (money was taken).
 *   - Only rows with no existing queue entry (ON CONFLICT also protects us).
 *   - Server ingest is idempotent on client_uuid, so a duplicate send is a
 *     no-op that returns "duplicate".
 *   - Runs once; guarded by a kv_meta flag.
 */

import { getDb } from "./client";

const FLAG = "backfill.unqueued_paid_sales.v1";

interface Row {
  id: string;
  client_uuid: string;
  is_held: number;
}

export function backfillUnqueuedPaidSales(): { scanned: number; queued: number } {
  const db = getDb();

  const done = db
    .prepare("SELECT value FROM kv_meta WHERE key = ?")
    .get(FLAG) as { value: string } | undefined;
  if (done) return { scanned: 0, queued: 0 };

  // A sale that took money but has no outbound_queue row: the enqueue was
  // skipped by the old early-return.
  const rows = db
    .prepare(
      `SELECT i.id, i.client_uuid, i.is_held
         FROM invoices i
        WHERE EXISTS (
                SELECT 1 FROM payments p
                 WHERE p.invoice_id = i.id AND p.status = 'completed'
              )
          AND NOT EXISTS (
                SELECT 1 FROM outbound_queue q
                 WHERE q.client_uuid = i.client_uuid
              )`,
    )
    .all() as Row[];

  const insertQueueRow = db.prepare(
    `INSERT INTO outbound_queue (
       client_uuid, entity_type, entity_id, action, payload, next_attempt_at
     ) VALUES (?, 'invoice', ?, 'create', ?, datetime('now'))
     ON CONFLICT(client_uuid) DO NOTHING`,
  );
  const getInvoice = db.prepare(`SELECT * FROM invoices WHERE id = ?`);
  const getItems = db.prepare(
    `SELECT * FROM sale_items WHERE invoice_id = ? ORDER BY line_number`,
  );
  const getPayments = db.prepare(`SELECT * FROM payments WHERE invoice_id = ?`);

  let queued = 0;
  const tx = db.transaction(() => {
    for (const r of rows) {
      const invoice = getInvoice.get(r.id) as Record<string, unknown>;
      const items = getItems.all(r.id) as Record<string, unknown>[];
      const payments = getPayments.all(r.id) as Record<string, unknown>[];

      // Rebuild the wire shape the server's ingest expects. Mirrors the
      // syncPayload built at Charge in payment.tsx.
      const payload = {
        client_uuid: r.client_uuid,
        local_invoice_number: invoice.local_invoice_number,
        branch: invoice.branch_id,
        terminal: invoice.terminal_id,
        cashier: invoice.cashier_id,
        cash_session: invoice.cash_session_id,
        customer: invoice.customer_id,
        notes: invoice.notes,
        order_type: invoice.order_type ?? null,
        table: invoice.table_id ?? null,
        covers: invoice.covers ?? null,
        cart_lines: items.map((it) => ({
          product: it.product_id,
          quantity: it.quantity,
          unit_price: it.unit_price,
          discount_pct: it.discount_pct ?? 0,
          discount_amount: it.discount_amount ?? 0,
          tax_rate: it.tax_rate ?? 0,
          is_taxable: Number(it.tax_rate ?? 0) > 0,
          modifiers: it.modifiers ? JSON.parse(String(it.modifiers)) : [],
          item_note: it.item_note ?? null,
        })),
        payments: payments.map((p) => ({
          payment_method: p.payment_method,
          amount: p.amount,
          card_last4: p.card_last4 ?? null,
          card_auth_code: p.card_auth_code ?? null,
        })),
      };

      // A charged sale must not still be flagged held locally.
      if (r.is_held === 1) {
        db.prepare(
          `UPDATE invoices SET is_held = 0, held_label = NULL, updated_at = ?
            WHERE id = ?`,
        ).run(new Date().toISOString(), r.id);
      }

      insertQueueRow.run(r.client_uuid, r.id, JSON.stringify(payload));
      queued += 1;
    }
    db.prepare(
      `INSERT INTO kv_meta(key, value, updated_at)
       VALUES (?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                      updated_at=CURRENT_TIMESTAMP`,
    ).run(FLAG, new Date().toISOString());
  });
  tx();

  return { scanned: rows.length, queued };
}
