/**
 * Thermal printer adapter — Phase 2.
 *
 * Real ESC/POS printing via node-thermal-printer is added in Phase 8 along
 * with the hardware certification matrix. For Phase 2 we ship a graceful
 * "no printer attached" code path that:
 *   - logs the rendered receipt to a file under userData/
 *   - returns success: false with a reason
 *   - never blocks the cashier
 *
 * The receipt template is shaped now (80mm + 58mm widths) so swapping the
 * actual transport in Phase 8 is a one-file change.
 */

import { app } from "electron";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import type { PosInvoiceInput, PosSaleItemInput, PosPaymentInput } from "./db/sales";

interface ReceiptInput {
  business_name: string;
  branch_name: string;
  ntn: string;
  address?: string;
  invoice: PosInvoiceInput;
  items: PosSaleItemInput[];
  payments: PosPaymentInput[];
  width: 48 | 32;   // 80mm or 58mm
}

interface PrintResult {
  success: boolean;
  reason?: string;
  fallbackPath?: string;
}

const TIMEOUT_MS = 5000;

export async function printReceipt(input: ReceiptInput): Promise<PrintResult> {
  const rendered = renderReceiptText(input);

  // Try the real printer first. In Phase 2 we don't have node-thermal-printer
  // wired up, so this always falls through. Phase 8 lights it up.
  const realPrintAttempted = false;
  if (!realPrintAttempted) {
    const fallback = writeFallback(input.invoice.id, rendered);
    return {
      success: false,
      reason: "no printer attached (dev fallback)",
      fallbackPath: fallback,
    };
  }

  // Reserved for Phase 8.
  return await Promise.race([
    realPrint(rendered, input.width),
    new Promise<PrintResult>((resolve) =>
      setTimeout(() => resolve({ success: false, reason: "timeout" }), TIMEOUT_MS),
    ),
  ]);
}

export async function openCashDrawer(): Promise<{ success: boolean; reason?: string }> {
  // Phase 2 dev fallback: log the event. Phase 8 sends ESC p 0 25 250 via the
  // attached printer.
  // eslint-disable-next-line no-console
  console.log("[drawer] would open cash drawer");
  return { success: false, reason: "no printer attached" };
}

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

function renderReceiptText(input: ReceiptInput): string {
  const W = input.width;
  const lines: string[] = [];
  const center = (s: string) => s.length >= W ? s : " ".repeat(Math.floor((W - s.length) / 2)) + s;
  const rule = "-".repeat(W);

  lines.push(center(input.business_name.toUpperCase()));
  if (input.address) lines.push(center(input.address));
  lines.push(center(`NTN: ${input.ntn}`));
  lines.push(center(input.branch_name));
  lines.push(rule);

  lines.push(`Invoice: ${input.invoice.local_invoice_number}`);
  lines.push(`Date:    ${input.invoice.invoice_date}`);
  if (input.invoice.buyer_name) {
    lines.push(`Buyer:   ${input.invoice.buyer_name}`);
  }
  lines.push(rule);

  for (const it of input.items) {
    lines.push(it.product_name.slice(0, W));
    const left = `  ${it.quantity} × ${it.unit_price}`;
    const right = it.line_total;
    const pad = Math.max(1, W - left.length - right.length);
    lines.push(left + " ".repeat(pad) + right);
  }
  lines.push(rule);

  const totals: [string, string][] = [
    ["Subtotal", input.invoice.subtotal],
    ["Discount", input.invoice.discount_total],
    ["Tax", input.invoice.tax_total],
    ["TOTAL", input.invoice.grand_total],
    ["Tendered", input.invoice.paid_total],
    ["Change", input.invoice.change_given],
  ];
  for (const [k, v] of totals) {
    const pad = Math.max(1, W - k.length - v.length);
    lines.push(k + " ".repeat(pad) + v);
  }
  lines.push(rule);

  for (const p of input.payments) {
    const k = `Paid: ${p.payment_method}`;
    const pad = Math.max(1, W - k.length - p.amount.length);
    lines.push(k + " ".repeat(pad) + p.amount);
  }
  lines.push(rule);

  lines.push(center("Thank you!"));
  lines.push("");
  return lines.join("\n");
}

function writeFallback(invoiceId: string, text: string): string {
  const dir = path.join(app.getPath("userData"), "receipts-dev");
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${invoiceId}.txt`);
  writeFileSync(file, text, "utf8");
  return file;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function realPrint(_text: string, _width: 48 | 32): Promise<PrintResult> {
  // Phase 8 placeholder.
  return { success: false, reason: "real printer not wired in this phase" };
}
