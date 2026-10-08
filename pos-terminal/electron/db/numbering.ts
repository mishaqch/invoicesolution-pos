/**
 * Local invoice number generator.
 *
 * Format mirrors the server (BRANCH-T#-YYYY-NNNN). Counter lives in
 * kv_meta keyed by (terminal, year). Increment is atomic via a
 * better-sqlite3 transaction.
 */

import { getDb } from "./client";

const FORMAT_VERSION = 1;

interface ResolveArgs {
  branchCode: string;
  terminalIndex: number; // 1, 2, …
}

export function nextInvoiceNumber(args: ResolveArgs): string {
  const year = new Date().getFullYear();
  const key = `invoice_seq:${args.branchCode}:T${args.terminalIndex}:${year}`;
  const db = getDb();
  const tx = db.transaction((k: string) => {
    const row = db.prepare("SELECT value FROM kv_meta WHERE key = ?").get(k) as
      | { value: string }
      | undefined;
    const next = (row ? parseInt(row.value, 10) : 0) + 1;
    db.prepare(
      `INSERT INTO kv_meta(key, value, updated_at)
       VALUES(?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
    ).run(k, next.toString());
    return next;
  });
  const seq = tx(key);
  const padded = seq.toString().padStart(7, "0");
  return `${args.branchCode}-T${args.terminalIndex}-${year}-${padded}`;
}

/**
 * Hand a minted number BACK when its order is abandoned.
 *
 * The counter advances the moment a number is requested — at fire/hold time,
 * so the KOT, the open-order card and the final bill all carry one number.
 * Nothing ever returned it, so every voided or abandoned order burned a
 * number and left a permanent hole in the daily sequence (0908, 0914, 0919,
 * 0934 on T3 in one day).
 *
 * Only the MOST RECENT number can be released: rolling back any earlier one
 * would re-issue a number already printed on a kitchen slip. So this is a
 * conditional decrement — if another order has since taken a number, the gap
 * is genuine and we leave it alone rather than risk a duplicate.
 */
export function releaseInvoiceNumber(args: ResolveArgs & { number: string }): boolean {
  const year = new Date().getFullYear();
  const key = `invoice_seq:${args.branchCode}:T${args.terminalIndex}:${year}`;
  const tail = args.number.split("-").pop();
  const seq = Number.parseInt(String(tail ?? ""), 10);
  if (!Number.isFinite(seq) || seq <= 0) return false;

  const db = getDb();
  const tx = db.transaction(() => {
    const row = db.prepare("SELECT value FROM kv_meta WHERE key = ?").get(key) as
      | { value: string }
      | undefined;
    const current = row ? parseInt(row.value, 10) : 0;
    // Only roll back if this was the last number issued.
    if (current !== seq) return false;
    db.prepare(
      `INSERT INTO kv_meta(key, value, updated_at)
       VALUES(?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
    ).run(key, String(seq - 1));
    return true;
  });
  return tx();
}

/**
 * A short, human-friendly KITCHEN ORDER number that resets each day: 001, 002,
 * 003 … Used on the KOT and the "Open orders" card so cooks/cashiers can call
 * out "Order 3" instead of a hex id. Atomic increment; keyed by the local date
 * so the count restarts at 001 every morning. Zero-padded to 3 digits (rolls
 * over to 4+ digits past 999, still readable).
 */
export function nextKitchenOrderNumber(): string {
  const now = new Date();
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const key = `kitchen_order_seq:${day}`;
  const db = getDb();
  const tx = db.transaction((k: string) => {
    const row = db.prepare("SELECT value FROM kv_meta WHERE key = ?").get(k) as
      | { value: string }
      | undefined;
    const next = (row ? parseInt(row.value, 10) : 0) + 1;
    db.prepare(
      `INSERT INTO kv_meta(key, value, updated_at)
       VALUES(?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`,
    ).run(k, next.toString());
    return next;
  });
  const seq = tx(key);
  return seq.toString().padStart(3, "0");
}

export const _internalFormatVersion = FORMAT_VERSION;
