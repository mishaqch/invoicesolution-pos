/**
 * Thermal printer adapter (ESC/POS).
 *
 * Drives a real thermal printer when `POS_PRINTER_INTERFACE` is set —
 * USB device path, TCP host:port, or serial path — and falls back to
 * writing the rendered receipt to `userData/receipts-dev/<invoice>.txt`
 * when no printer is configured. The cashier flow never blocks on
 * hardware: every print attempt is wrapped in a 5s timeout.
 *
 * Cash drawer: ESC p 0 25 250 emitted via the attached printer's drawer
 * kick port (the standard hardware path on USB/network thermal printers).
 *
 * Configuration (any one of these resolved at print time, in priority order):
 *   1. POS_PRINTER_INTERFACE env var (e.g. "tcp://192.168.1.50:9100",
 *      "/dev/usb/lp0", "//USB/EPSON-TM-T20III")
 *   2. Local SQLite meta key "printer.interface" (set via Hardware
 *      settings page)
 *   3. None — fallback path
 *
 * Optional env vars:
 *   - POS_PRINTER_DIALECT  "epson" (default) or "star"
 *   - POS_PRINTER_CHARSET  "PC437_USA" (default), "WPC1252", etc.
 *
 * Tested against EPSON TM-T20III + Xprinter XP-58. Prebuilt binaries via
 * node-thermal-printer cover the common Pakistan-market models.
 */

import { app } from "electron";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { getMeta } from "./db/client";
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


// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

function resolvePrinterInterface(): string | null {
  const env = process.env["POS_PRINTER_INTERFACE"];
  if (env && env.trim()) return env.trim();
  try {
    const meta = getMeta("printer.interface");
    if (meta && meta.trim()) return meta.trim();
  } catch {
    // SQLite not initialized yet (early call). Treat as no printer.
  }
  return null;
}

function resolveDialect(): "epson" | "star" {
  const v = (process.env["POS_PRINTER_DIALECT"] || "").toLowerCase();
  return v === "star" ? "star" : "epson";
}

function resolveCharset(): string {
  return process.env["POS_PRINTER_CHARSET"] || "PC437_USA";
}


// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function printReceipt(input: ReceiptInput): Promise<PrintResult> {
  const rendered = renderReceiptText(input);
  const printerUrl = resolvePrinterInterface();

  if (!printerUrl) {
    const fallback = writeFallback(input.invoice.id, rendered);
    return {
      success: false,
      reason: "no printer configured (set POS_PRINTER_INTERFACE)",
      fallbackPath: fallback,
    };
  }

  return withTimeout(realPrint(rendered, input, printerUrl), TIMEOUT_MS, () => {
    // Timeout fallback: still log to disk so the receipt isn't lost.
    const fallback = writeFallback(input.invoice.id, rendered);
    return {
      success: false,
      reason: "printer timeout (5s) — logged to disk",
      fallbackPath: fallback,
    };
  });
}

export async function openCashDrawer(): Promise<{ success: boolean; reason?: string }> {
  const printerUrl = resolvePrinterInterface();
  if (!printerUrl) {
    console.log("[drawer] no printer configured; cannot open drawer");
    return { success: false, reason: "no printer configured" };
  }
  return withTimeout(realOpenDrawer(printerUrl), TIMEOUT_MS, () => ({
    success: false,
    reason: "drawer timeout (5s)",
  }));
}


// ---------------------------------------------------------------------------
// Real printing via node-thermal-printer
// ---------------------------------------------------------------------------

async function realPrint(
  text: string,
  input: ReceiptInput,
  printerUrl: string,
): Promise<PrintResult> {
  // Lazy require so the module loads even when the native deps fail
  // to compile on dev machines without a printer.
  let mod: any;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    mod = require("node-thermal-printer");
  } catch (e) {
    console.error("[printer] node-thermal-printer unavailable:", e);
    return { success: false, reason: "printer driver not installed" };
  }

  const ThermalPrinter = mod.printer;
  const PrinterTypes = mod.types;
  const printer = new ThermalPrinter({
    type: resolveDialect() === "star" ? PrinterTypes.STAR : PrinterTypes.EPSON,
    interface: printerUrl,
    characterSet: PrinterTypes.CharacterSet?.[resolveCharset()] ?? undefined,
    width: input.width,
    options: { timeout: TIMEOUT_MS },
  });

  const ok = await printer.isPrinterConnected();
  if (!ok) {
    console.error("[printer] not reachable at", printerUrl);
    return { success: false, reason: `printer unreachable at ${printerUrl}` };
  }

  for (const line of text.split("\n")) {
    printer.println(line);
  }

  // Optional FBR QR: if the invoice carries an FBR QR payload, embed it.
  // Falls back silently when payload is absent.
  const qrPayload = (input.invoice as { fbr_qr_payload?: string | null }).fbr_qr_payload;
  if (qrPayload) {
    printer.alignCenter();
    try {
      await printer.printQR(qrPayload, { cellSize: 6 });
      printer.println("Scan to verify on FBR");
    } catch (e) {
      console.warn("[printer] QR render failed:", e);
    }
    printer.alignLeft();
  }

  printer.cut();
  await printer.execute();

  return { success: true };
}

async function realOpenDrawer(
  printerUrl: string,
): Promise<{ success: boolean; reason?: string }> {
  let mod: any;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    mod = require("node-thermal-printer");
  } catch {
    return { success: false, reason: "printer driver not installed" };
  }
  const ThermalPrinter = mod.printer;
  const PrinterTypes = mod.types;
  const printer = new ThermalPrinter({
    type: resolveDialect() === "star" ? PrinterTypes.STAR : PrinterTypes.EPSON,
    interface: printerUrl,
    options: { timeout: TIMEOUT_MS },
  });

  const ok = await printer.isPrinterConnected();
  if (!ok) {
    return { success: false, reason: `printer unreachable at ${printerUrl}` };
  }
  printer.openCashDrawer();   // ESC p 0 25 250 under the hood
  await printer.execute();
  return { success: true };
}


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  onTimeout: () => T,
): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((resolve) => setTimeout(() => resolve(onTimeout()), ms)),
  ]);
}


// ---------------------------------------------------------------------------
// Renderer (text-mode receipt body — same for real + fallback paths)
// ---------------------------------------------------------------------------

function renderReceiptText(input: ReceiptInput): string {
  const W = input.width;
  const lines: string[] = [];
  const center = (s: string) =>
    s.length >= W ? s : " ".repeat(Math.floor((W - s.length) / 2)) + s;
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
  const fbrNum = (input.invoice as { fbr_invoice_number?: string | null })
    .fbr_invoice_number;
  if (fbrNum) {
    lines.push(`FBR:     ${fbrNum}`);
  }
  lines.push(rule);

  for (const it of input.items) {
    lines.push(it.product_name.slice(0, W));
    const left = `  ${it.quantity} x ${it.unit_price}`;
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

// Unit-test entry — exposed for the renderer formatter test.
export const __testing = { renderReceiptText };
