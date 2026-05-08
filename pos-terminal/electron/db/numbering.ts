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
  terminalIndex: number;   // 1, 2, …
}

export function nextInvoiceNumber(args: ResolveArgs): string {
  const year = new Date().getFullYear();
  const key = `invoice_seq:${args.branchCode}:T${args.terminalIndex}:${year}`;
  const db = getDb();
  const tx = db.transaction((k: string) => {
    const row = db
      .prepare("SELECT value FROM kv_meta WHERE key = ?")
      .get(k) as { value: string } | undefined;
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

export const _internalFormatVersion = FORMAT_VERSION;
