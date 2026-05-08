/**
 * Sales persistence on the POS terminal.
 *
 * The cashier never blocks on the network: we write everything to local
 * SQLite first, then enqueue a sync row. Phase 3 will replace the no-op
 * sync worker with the real one.
 */

import { getDb } from "./client";

export interface PosCashSession {
  id: string;
  branch_id: string;
  terminal_id: string;
  cashier_id: string;
  opened_at: string;
  opened_with_amount: string;
  closed_at: string | null;
  closed_with_amount: string | null;
  expected_amount: string | null;
  variance: string | null;
  variance_reason: string | null;
  total_sales: string;
  cash_in: string;
  cash_out: string;
  status: "open" | "closed";
}

export interface PosInvoiceInput {
  id: string;
  client_uuid: string;
  local_invoice_number: string;
  invoice_date: string;             // ISO date
  customer_id: string | null;
  buyer_name: string | null;
  buyer_phone: string | null;
  buyer_ntn_cnic: string | null;
  buyer_registration_type: string | null;
  branch_id: string;
  terminal_id: string;
  cashier_id: string;
  cash_session_id: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  change_given: string;
  notes: string | null;
}

export interface PosSaleItemInput {
  id: string;
  invoice_id: string;
  line_number: number;
  product_id: string;
  product_name: string;
  product_sku: string;
  uom_code: string;
  hs_code: string | null;
  quantity: string;
  unit_price: string;
  discount_pct: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  line_total: string;
  notes: string | null;
}

export interface PosPaymentInput {
  id: string;
  invoice_id: string;
  payment_method: string;
  amount: string;
  status?: "pending" | "completed" | "failed" | "refunded";
}

export function openCashSession(input: PosCashSession): void {
  getDb()
    .prepare(
      `INSERT INTO cash_sessions
         (id, branch_id, terminal_id, cashier_id, opened_at, opened_with_amount,
          total_sales, cash_in, cash_out, status)
       VALUES (@id, @branch_id, @terminal_id, @cashier_id, @opened_at,
               @opened_with_amount, '0', '0', '0', 'open')`,
    )
    .run(input);
}

export function getOpenSession(terminal_id: string): PosCashSession | null {
  const row = getDb()
    .prepare(`SELECT * FROM cash_sessions WHERE terminal_id = ? AND status = 'open'`)
    .get(terminal_id) as PosCashSession | undefined;
  return row ?? null;
}

export function closeCashSession(
  id: string,
  args: {
    closed_at: string;
    closed_with_amount: string;
    expected_amount: string;
    variance: string;
    variance_reason: string;
  },
): void {
  getDb()
    .prepare(
      `UPDATE cash_sessions SET
         closed_at=@closed_at, closed_with_amount=@closed_with_amount,
         expected_amount=@expected_amount, variance=@variance,
         variance_reason=@variance_reason, status='closed'
       WHERE id=@id`,
    )
    .run({ id, ...args });
}

export function totalsForSession(session_id: string): { total_sales: string } {
  const row = getDb()
    .prepare(
      `SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) AS total
       FROM payments p
       JOIN invoices i ON i.id = p.invoice_id
       WHERE i.cash_session_id = ? AND p.payment_method = 'cash'
         AND p.status = 'completed' AND i.status != 'cancelled'`,
    )
    .get(session_id) as { total: number } | undefined;
  return { total_sales: ((row?.total ?? 0).toFixed(4)) };
}

interface PersistInvoiceArgs {
  invoice: PosInvoiceInput;
  items: PosSaleItemInput[];
  payments: PosPaymentInput[];
  is_held?: boolean;
  held_label?: string | null;
}

export function persistInvoice(args: PersistInvoiceArgs): void {
  const db = getDb();
  const now = new Date().toISOString();

  const insertInvoice = db.prepare(`
    INSERT INTO invoices (
      id, client_uuid, local_invoice_number, status, invoice_date,
      customer_id, buyer_name, buyer_phone, buyer_ntn_cnic, buyer_registration_type,
      branch_id, terminal_id, cashier_id, cash_session_id,
      subtotal, discount_total, tax_total, grand_total, paid_total, change_given,
      is_held, held_label, notes, created_at, updated_at
    ) VALUES (
      @id, @client_uuid, @local_invoice_number, @status, @invoice_date,
      @customer_id, @buyer_name, @buyer_phone, @buyer_ntn_cnic, @buyer_registration_type,
      @branch_id, @terminal_id, @cashier_id, @cash_session_id,
      @subtotal, @discount_total, @tax_total, @grand_total, @paid_total, @change_given,
      @is_held, @held_label, @notes, @created_at, @updated_at
    )
  `);
  const insertItem = db.prepare(`
    INSERT INTO sale_items (
      id, invoice_id, line_number,
      product_id, product_name, product_sku, uom_code, hs_code,
      quantity, unit_price, discount_pct, discount_amount,
      tax_rate, tax_amount, line_total, notes
    ) VALUES (
      @id, @invoice_id, @line_number,
      @product_id, @product_name, @product_sku, @uom_code, @hs_code,
      @quantity, @unit_price, @discount_pct, @discount_amount,
      @tax_rate, @tax_amount, @line_total, @notes
    )
  `);
  const insertPayment = db.prepare(`
    INSERT INTO payments (id, invoice_id, payment_method, amount, status, created_at)
    VALUES (@id, @invoice_id, @payment_method, @amount, @status, @created_at)
  `);
  const insertQueueRow = db.prepare(`
    INSERT INTO outbound_queue (
      client_uuid, entity_type, entity_id, action, payload, next_attempt_at
    ) VALUES (?, 'invoice', ?, 'create', ?, datetime('now'))
    ON CONFLICT(client_uuid) DO NOTHING
  `);

  const tx = db.transaction(() => {
    insertInvoice.run({
      ...args.invoice,
      status: args.is_held ? "pending_sync" : "pending_sync",
      is_held: args.is_held ? 1 : 0,
      held_label: args.held_label ?? null,
      created_at: now,
      updated_at: now,
    });
    for (const item of args.items) insertItem.run({ ...item, notes: item.notes ?? null });
    for (const p of args.payments) {
      insertPayment.run({
        status: "completed",
        created_at: now,
        ...p,
      });
    }

    if (!args.is_held) {
      // Only enqueue completed sales for sync; held sales stay local until
      // the cashier actually charges them.
      insertQueueRow.run(
        args.invoice.client_uuid,
        args.invoice.id,
        JSON.stringify({
          invoice: args.invoice,
          items: args.items,
          payments: args.payments,
        }),
      );
    }
  });
  tx();
}

export function listInvoices(opts: { held?: boolean; limit?: number } = {}) {
  const db = getDb();
  if (opts.held === true) {
    return db
      .prepare(
        `SELECT * FROM invoices WHERE is_held = 1
         ORDER BY datetime(created_at) DESC
         LIMIT ?`,
      )
      .all(opts.limit ?? 50);
  }
  return db
    .prepare(
      `SELECT * FROM invoices WHERE is_held = 0
       ORDER BY datetime(created_at) DESC
       LIMIT ?`,
    )
    .all(opts.limit ?? 50);
}

export function getInvoiceWithLines(invoice_id: string) {
  const db = getDb();
  const invoice = db.prepare(`SELECT * FROM invoices WHERE id = ?`).get(invoice_id) as
    | Record<string, unknown>
    | undefined;
  if (!invoice) return null;
  const items = db
    .prepare(`SELECT * FROM sale_items WHERE invoice_id = ? ORDER BY line_number`)
    .all(invoice_id);
  const payments = db
    .prepare(`SELECT * FROM payments WHERE invoice_id = ?`)
    .all(invoice_id);
  return { invoice, items, payments };
}

export function holdInvoice(invoice_id: string, label: string): void {
  getDb()
    .prepare(
      `UPDATE invoices SET is_held = 1, held_label = ?, updated_at = ?
       WHERE id = ?`,
    )
    .run(label, new Date().toISOString(), invoice_id);
}

export function recallInvoice(invoice_id: string): void {
  getDb()
    .prepare(
      `UPDATE invoices SET is_held = 0, held_label = NULL, updated_at = ?
       WHERE id = ?`,
    )
    .run(new Date().toISOString(), invoice_id);
}
