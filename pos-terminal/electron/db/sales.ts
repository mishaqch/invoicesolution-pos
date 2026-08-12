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
  /** FEFO batch this line drew from (pharmacy). NULL for ordinary products. */
  batch_id?: string | null;
  /** Restaurant: chosen modifiers (array, stored as JSON) + kitchen note. */
  modifiers?: { name: string; price: string }[];
  item_note?: string | null;
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
  /** API-shape body that the sync worker will POST to /api/sync/invoices/.
   *  If omitted, the worker won't have the right wire format — pass it. */
  syncPayload?: Record<string, unknown>;
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
      tax_rate, tax_amount, line_total, notes, batch_id, modifiers, item_note
    ) VALUES (
      @id, @invoice_id, @line_number,
      @product_id, @product_name, @product_sku, @uom_code, @hs_code,
      @quantity, @unit_price, @discount_pct, @discount_amount,
      @tax_rate, @tax_amount, @line_total, @notes, @batch_id, @modifiers, @item_note
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

  // IDEMPOTENCY: client_uuid is UNIQUE and is the sale's stable idempotency key.
  // If a row with this client_uuid already exists, this is a re-submit of the
  // SAME sale (e.g. the cashier double-tapped "Complete sale", or a retry after
  // a partial failure). Return the existing id instead of throwing the raw
  // "UNIQUE constraint failed: invoices.client_uuid" SqliteError at the till.
  const existing = db
    .prepare("SELECT id FROM invoices WHERE client_uuid = ?")
    .get(args.invoice.client_uuid) as { id: string } | undefined;
  if (existing) {
    return;
  }

  const tx = db.transaction(() => {
    insertInvoice.run({
      ...args.invoice,
      status: args.is_held ? "pending_sync" : "pending_sync",
      is_held: args.is_held ? 1 : 0,
      held_label: args.held_label ?? null,
      created_at: now,
      updated_at: now,
    });
    for (const item of args.items) {
      insertItem.run({
        ...item,
        notes: item.notes ?? null,
        batch_id: item.batch_id ?? null,
        // better-sqlite3 can't bind arrays/objects — store modifiers as JSON.
        modifiers: item.modifiers && item.modifiers.length ? JSON.stringify(item.modifiers) : null,
        item_note: item.item_note ?? null,
      });
    }
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
      const payload = args.syncPayload ?? {
        invoice: args.invoice, items: args.items, payments: args.payments,
      };
      insertQueueRow.run(
        args.invoice.client_uuid,
        args.invoice.id,
        JSON.stringify(payload),
      );
    }
  });
  tx();
}

/**
 * Mirror a SERVER-created invoice into local SQLite for display (e.g. hotel
 * folio room/restaurant charges, which are created server-side, not through the
 * offline checkout path). Unlike persistInvoice() this does NOT enqueue a sync
 * row — the server already owns the record; we only cache it so it shows up in
 * "Today's invoices" and can be reprinted offline. Idempotent: re-mirroring the
 * same invoice id replaces the cached copy (INSERT OR REPLACE).
 */
export function persistServerInvoice(args: {
  invoice: PosInvoiceInput & {
    status?: string;
    fbr_invoice_number?: string | null;
    fbr_qr_payload?: string | null;
    created_at?: string | null;
  };
  items: PosSaleItemInput[];
  payments: PosPaymentInput[];
}): void {
  const db = getDb();
  const now = new Date().toISOString();
  const createdAt = args.invoice.created_at || now;

  const upInvoice = db.prepare(`
    INSERT OR REPLACE INTO invoices (
      id, client_uuid, local_invoice_number, status, invoice_date,
      customer_id, buyer_name, buyer_phone, buyer_ntn_cnic, buyer_registration_type,
      branch_id, terminal_id, cashier_id, cash_session_id,
      subtotal, discount_total, tax_total, grand_total, paid_total, change_given,
      is_held, held_label, notes, fbr_invoice_number, fbr_qr_payload,
      created_at, updated_at
    ) VALUES (
      @id, @client_uuid, @local_invoice_number, @status, @invoice_date,
      @customer_id, @buyer_name, @buyer_phone, @buyer_ntn_cnic, @buyer_registration_type,
      @branch_id, @terminal_id, @cashier_id, @cash_session_id,
      @subtotal, @discount_total, @tax_total, @grand_total, @paid_total, @change_given,
      0, @held_label, @notes, @fbr_invoice_number, @fbr_qr_payload,
      @created_at, @updated_at
    )
  `);
  const delItems = db.prepare(`DELETE FROM sale_items WHERE invoice_id = ?`);
  const delPays = db.prepare(`DELETE FROM payments WHERE invoice_id = ?`);
  const insItem = db.prepare(`
    INSERT INTO sale_items (
      id, invoice_id, line_number,
      product_id, product_name, product_sku, uom_code, hs_code,
      quantity, unit_price, discount_pct, discount_amount,
      tax_rate, tax_amount, line_total, notes, batch_id, modifiers, item_note
    ) VALUES (
      @id, @invoice_id, @line_number,
      @product_id, @product_name, @product_sku, @uom_code, @hs_code,
      @quantity, @unit_price, @discount_pct, @discount_amount,
      @tax_rate, @tax_amount, @line_total, @notes, @batch_id, @modifiers, @item_note
    )
  `);
  const insPay = db.prepare(`
    INSERT INTO payments (id, invoice_id, payment_method, amount, status, created_at)
    VALUES (@id, @invoice_id, @payment_method, @amount, @status, @created_at)
  `);

  const tx = db.transaction(() => {
    upInvoice.run({
      ...args.invoice,
      status: args.invoice.status ?? "pending_sync",
      held_label: null,
      fbr_invoice_number: args.invoice.fbr_invoice_number ?? null,
      fbr_qr_payload: args.invoice.fbr_qr_payload ?? null,
      created_at: createdAt,
      updated_at: now,
    });
    delItems.run(args.invoice.id);
    delPays.run(args.invoice.id);
    args.items.forEach((item, i) => {
      insItem.run({
        ...item,
        line_number: item.line_number ?? i + 1,
        notes: item.notes ?? null,
        batch_id: item.batch_id ?? null,
        modifiers: item.modifiers && item.modifiers.length ? JSON.stringify(item.modifiers) : null,
        item_note: item.item_note ?? null,
      });
    });
    for (const p of args.payments) {
      insPay.run({ status: "completed", created_at: createdAt, ...p });
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

export interface PendingSyncRow {
  id: number;
  client_uuid: string;
  entity_type: string;
  status: string;
  attempt_count: number;
  last_error: string | null;
  next_attempt_at: string | null;
  created_at: string;
  local_invoice_number: string | null;
  grand_total: string | null;
  invoice_date: string | null;
  fbr_invoice_number: string | null;
}

// Rows still in flight (not yet acked 'ok'), for the operator's pending-sync
// list. LEFT JOIN so non-invoice entities still show; failed rows surface
// first, then newest. Read-only — retry actions go through the manager.
export function listPendingSync(limit = 100): PendingSyncRow[] {
  return getDb()
    .prepare(
      `SELECT q.id, q.client_uuid, q.entity_type, q.status, q.attempt_count,
              q.last_error, q.next_attempt_at, q.created_at,
              i.local_invoice_number, i.grand_total, i.invoice_date,
              i.fbr_invoice_number
       FROM outbound_queue q
       LEFT JOIN invoices i
         ON i.id = q.entity_id AND q.entity_type = 'invoice'
       WHERE q.status IN ('pending', 'sent', 'failed')
       ORDER BY (q.status = 'failed') DESC, datetime(q.created_at) DESC
       LIMIT ?`,
    )
    .all(limit) as PendingSyncRow[];
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

/**
 * Persist the PRAL validation result onto the local invoice row. Called from
 * the renderer once `useFbrConfirmation` polls the central server and sees the
 * invoice go `valid` with an FBR invoice number. This is what makes an offline
 * reprint FBR-compliant: the number + QR payload come from the local row, not
 * from transient in-memory state that's lost on reload.
 *
 * Per the "PRAL response is the source of truth" invariant we only ever set
 * these (never clear them) and only when the server actually reports a number.
 */
export function setInvoiceFbrFields(args: {
  invoice_id: string;
  fbr_invoice_number: string;
  fbr_qr_payload: string | null;
  fbr_validated_at: string | null;
}): void {
  getDb()
    .prepare(
      `UPDATE invoices
         SET fbr_invoice_number = @fbr_invoice_number,
             fbr_qr_payload     = @fbr_qr_payload,
             fbr_validated_at   = @fbr_validated_at,
             status             = 'valid',
             updated_at         = @updated_at
       WHERE id = @invoice_id`,
    )
    .run({ ...args, updated_at: new Date().toISOString() });
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

/** Delete a held invoice + its lines. The held row exists only so the
 *  cashier can find the cart again; once they've recalled it back into
 *  the in-memory cart, the row can go away. The next checkout creates
 *  a fresh row with a new client_uuid + local_invoice_number.
 *
 *  Guard: refuses to delete a row that's already on the sync queue
 *  (i.e. was once a completed sale). Held rows by definition were
 *  never enqueued (see persistInvoice), so this guard fires only on
 *  unexpected callers.
 */
export function deleteHeldInvoice(invoice_id: string): void {
  const db = getDb();
  const tx = db.transaction(() => {
    const row = db
      .prepare(`SELECT is_held FROM invoices WHERE id = ?`)
      .get(invoice_id) as { is_held: number } | undefined;
    if (!row) return;
    if (row.is_held !== 1) return; // refuse to nuke a real sale
    db.prepare(`DELETE FROM sale_items WHERE invoice_id = ?`).run(invoice_id);
    db.prepare(`DELETE FROM payments WHERE invoice_id = ?`).run(invoice_id);
    db.prepare(`DELETE FROM invoices WHERE id = ?`).run(invoice_id);
  });
  tx();
}
