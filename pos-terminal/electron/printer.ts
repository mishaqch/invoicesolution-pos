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
import { buildFbrStampPng } from "./fbr-stamp";
import { isWindowsInterface, printRawWindows, windowsPrinterName } from "./win-print";
import type { PosInvoiceInput, PosSaleItemInput, PosPaymentInput } from "./db/sales";

interface ReceiptInput {
  business_name: string;
  branch_name: string;
  ntn: string;
  address?: string;
  contact?: string; // business phone / contact number (header)
  // Restaurant only — shown under the title so the customer sees dine-in/table.
  order_type?: string | null;
  table_name?: string | null;
  invoice: PosInvoiceInput;
  items: PosSaleItemInput[];
  payments: PosPaymentInput[];
  width: 48 | 32; // 80mm or 58mm
  // Non-fiscal tenants (fbr_connection_type="none", e.g. the TDCP resort) are
  // not connected to any tax authority. Their receipts must omit BOTH the FBR
  // QR/number block AND the "FBR pending" notice, and print a plain resort
  // footer instead. Defaults to fiscal (true) so every existing FBR tenant is
  // byte-for-byte unchanged.
  is_fiscal?: boolean;
}

// Shared formatters (used by both the styled print + the plain disk fallback).
function money2(s: string | number | null | undefined): string {
  const n = Number(s ?? 0);
  return Number.isFinite(n) ? n.toFixed(2) : "0.00";
}
/** Whole-rupee display for a HEADLINE printed total (450.08 -> "450"). Half-up.
 *  Presentation only — the stored / FBR amount is unchanged. */
function moneyWhole(s: string | number | null | undefined): string {
  const n = Number(s ?? 0);
  return Number.isFinite(n) ? String(Math.round(n)) : "0";
}
function qtyFmt(s: string | number | null | undefined): string {
  // Quantities are whole units on a retail receipt — show "2", "20", not
  // "2.0000". Keep up to 3 decimals only if the item is genuinely fractional
  // (e.g. 1.5 kg), otherwise integer.
  const n = Number(s ?? 0);
  if (!Number.isFinite(n)) return String(s ?? "");
  return Number.isInteger(n) ? String(n) : String(parseFloat(n.toFixed(3)));
}

interface PrintResult {
  success: boolean;
  reason?: string;
  fallbackPath?: string;
}

const TIMEOUT_MS = 5000;

// Printed in place of the FBR QR block when a sale was rung up offline and has
// no FBR invoice number yet. Once it syncs and FBR validates, the receipt is
// reprinted with the real QR + number (from Today's Invoices, or auto on the
// success screen if the cashier is still there).
const FBR_PENDING_NOTICE = "FBR: pending - added when online";

// Invisible marker prefixed to the folio bill's header text lines (business
// name / address / contact) so the printer can drop them when a logo image is
// printed at the top instead. Uses a control char that never appears in normal
// text and is stripped before printing.
const HEADER_TAG = "\x00HDR\x00";

// Caption printed centered + bold directly under the receipt logo image.
const RECEIPT_LOGO_CAPTION = "TDCP Resort Kallar Kahar";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/**
 * Read a POS_* config var. electron-vite statically replaces
 * `import.meta.env.POS_*` at BUILD time (from .env/.env.local), but does NOT
 * populate process.env for the main process — so reading process.env alone
 * left POS_PRINTER_INTERFACE undefined and the app reported "no printer
 * configured". Prefer the build-time value, then any runtime process.env.
 */
function envVar(name: string): string | undefined {
  const fromBuild = (import.meta.env as Record<string, string | undefined>)?.[name];
  return (fromBuild && String(fromBuild)) || process.env[name] || undefined;
}

function resolvePrinterInterface(): string | null {
  const env = envVar("POS_PRINTER_INTERFACE");
  if (env && env.trim()) return env.trim();
  try {
    const meta = getMeta("printer.interface");
    if (meta && meta.trim()) return meta.trim();
  } catch {
    // SQLite not initialized yet (early call). Treat as no printer.
  }
  return null;
}

/**
 * The KITCHEN printer — a SEPARATE physical printer (usually a network/WiFi
 * printer sitting in the kitchen). KOTs print here so the cook gets the order
 * without any PC/screen in the kitchen — just the printer.
 *
 * Resolution order: POS_KITCHEN_PRINTER_INTERFACE env → meta "kitchen.interface"
 * → null. There is DELIBERATELY no fallback to the counter printer: a KOT must
 * print ONLY on a dedicated kitchen printer. When none is configured the caller
 * saves the KOT to disk instead of printing it at the counter (which would put
 * a kitchen ticket on the customer's receipt roll).
 * The kitchen printer must be on the SAME network as the terminal (same router/
 * bridged extender) for the terminal to reach it by IP, e.g.
 * "tcp://192.168.0.60:9100" set in Hardware settings.
 */
function resolveKitchenPrinterInterface(): string | null {
  const env = envVar("POS_KITCHEN_PRINTER_INTERFACE");
  if (env && env.trim()) return env.trim();
  try {
    const meta = getMeta("kitchen.interface");
    if (meta && meta.trim()) return meta.trim();
  } catch {
    // SQLite not ready — treat as no kitchen printer.
  }
  // No dedicated kitchen printer → null (KOT saves to disk, never counter).
  return null;
}

function resolveDialect(): "epson" | "star" {
  const v = (envVar("POS_PRINTER_DIALECT") || "").toLowerCase();
  return v === "star" ? "star" : "epson";
}

function resolveCharset(): string {
  return envVar("POS_PRINTER_CHARSET") || "PC437_USA";
}

/**
 * Resolve the FBR Digital Invoicing logo bundled for the thermal receipt.
 * Mirrors the schema.sql candidate-path approach in db/client.ts: works from
 * the source tree in dev and from the asar/out layout in prod. Returns null if
 * the asset is missing so printing degrades to QR-only rather than failing.
 */
function resolveFbrLogoPath(): string | null {
  return resolveAssetPath("fbr-logo-thermal.png");
}

/** Resolve a bundled electron/assets file across dev + asar/out layouts. */
function resolveAssetPath(rel: string): string | null {
  const candidates = [
    // dev: cwd is the pos-terminal package root
    path.resolve(process.cwd(), "electron/assets", rel),
    // bundled next to main.cjs (if a copy step ever places it there)
    path.resolve(__dirname, "assets", rel),
    // prod asar: __dirname is out/main; the source-packaged asset sits at
    // <app.asar>/electron/assets — two levels up from out/main.
    path.resolve(__dirname, "../../electron/assets", rel),
    path.resolve(__dirname, "../electron/assets", rel),
  ];
  return candidates.find((p) => existsSync(p)) ?? null;
}

/**
 * The tenant's receipt-header logo, printed centered at the top of the bill
 * INSTEAD of the business-name text banner. Black, thermal-ready PNG (~384px
 * wide) bundled at electron/assets/receipt-logo.png. Returns null if absent, in
 * which case the print falls back to the text banner.
 */
function resolveReceiptLogoPath(): string | null {
  return resolveAssetPath("receipt-logo.png");
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function printReceipt(input: ReceiptInput): Promise<PrintResult> {
  const rendered = renderReceiptText(input);
  const printerUrl = resolvePrinterInterface();
  console.log("[printer] printReceipt — interface:", printerUrl ?? "(none)");

  if (!printerUrl) {
    const fallback = writeFallback(input.invoice.id, rendered);
    return {
      success: false,
      reason: "no printer configured (set POS_PRINTER_INTERFACE)",
      fallbackPath: fallback,
    };
  }

  // CUPS printing (rendering the logo+QR composite, then lp piping the bytes to
  // the spooler) can take longer than the 5s used for direct serial/tcp. Give
  // it a generous window so a working printer isn't falsely timed out to disk.
  const timeout = printerUrl.startsWith("cups://") ? 30_000 : TIMEOUT_MS;

  try {
    return await withTimeout(realPrint(rendered, input, printerUrl), timeout, () => {
      console.warn("[printer] realPrint timed out after", timeout, "ms");
      const fallback = writeFallback(input.invoice.id, rendered);
      return {
        success: false,
        reason: `printer timeout (${timeout / 1000}s) — logged to disk`,
        fallbackPath: fallback,
      };
    });
  } catch (e) {
    console.error("[printer] realPrint threw:", e);
    const fallback = writeFallback(input.invoice.id, rendered);
    return {
      success: false,
      reason: `print error: ${e instanceof Error ? e.message : String(e)}`,
      fallbackPath: fallback,
    };
  }
}

/**
 * Print a short diagnostic slip on demand (Hardware → Test print). Optionally
 * overrides the saved interface so the operator can verify a printer BEFORE
 * saving. Returns the same PrintResult shape (with a fallback file path when no
 * printer is reachable) so the UI can show a precise reason.
 */
export async function testPrint(overrideInterface?: string): Promise<PrintResult> {
  const printerUrl = (overrideInterface && overrideInterface.trim()) || resolvePrinterInterface();
  if (!printerUrl) {
    return { success: false, reason: "no printer configured" };
  }
  const now = new Date();
  const lines = [
    "     *** TEST PRINT ***",
    "",
    "invoiceSolution POS",
    `Interface: ${printerUrl}`,
    `Time: ${now.toLocaleString()}`,
    "",
    "If you can read this, the",
    "printer is working.",
    "",
    "0123456789  ABCDEFGHIJ",
    "Rs 1,234.56   x2   18%",
    "",
  ].join("\n");

  const transport = resolveTransport(printerUrl);
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
    interface: transport.ctorInterface,
    characterSet: PrinterTypes.CharacterSet?.[resolveCharset()] ?? undefined,
    width: 48,
    options: { timeout: TIMEOUT_MS },
  });
  try {
    if (transport.kind === "direct") {
      const ok = await printer.isPrinterConnected();
      if (!ok) return { success: false, reason: `printer unreachable at ${printerUrl}` };
    }
    for (const l of lines.split("\n")) printer.println(l);
    printer.cut();
    if (transport.kind !== "direct") return await flushBuffer(transport, printer.getBuffer());
    await printer.execute();
    return { success: true };
  } catch (e) {
    return {
      success: false,
      reason: `test print failed: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
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
// Kitchen Order Ticket (KOT) — restaurant vertical
// ---------------------------------------------------------------------------

interface KotItem {
  product_name: string;
  quantity: string | number;
  modifiers?: { name: string }[];
  item_note?: string | null;
}
interface KotInput {
  order_number: string; // local invoice / order #
  order_type: string; // dine_in / takeaway / delivery
  table_name?: string | null;
  covers?: number | null;
  time: string; // "19:32"
  items: KotItem[]; // ONLY the newly-fired items
  width: 48 | 32;
  // A human reference for the order (the cashier's label, e.g. "Ahmed"). Shown
  // as the destination when there is no table, so the kitchen sees a meaningful
  // name instead of a hex order id.
  reference?: string | null;
  // True when this ticket adds items to an order ALREADY sent to the kitchen —
  // prints a loud "ADDITIONAL ORDER" banner so the cook knows it's a follow-up
  // to the same order (same order_number), not a brand-new order.
  is_additional?: boolean;
  // True when the cashier VOIDED an order that was already sent to the kitchen —
  // prints a loud "VOID / CANCELLED" banner so the cook STOPS preparing it. The
  // items list is the order's items (what to cancel), not new items.
  is_void?: boolean;
}

/**
 * Print a Kitchen Order Ticket. This is NOT a fiscal document — no prices, no
 * FBR, never sent to PRAL. Big, scannable item names + modifiers + note for the
 * line cook. Reuses the same ESC/POS printer path as the receipt; falls back to
 * disk when no printer is configured (so kitchen orders are never lost).
 */
export async function printKOT(input: KotInput): Promise<PrintResult> {
  // KOTs go to the KITCHEN printer (separate network printer when configured;
  // falls back to the counter printer when it isn't). This is what auto-prints
  // in the kitchen when the cashier sends an order to the kitchen.
  const printerUrl = resolveKitchenPrinterInterface();
  const plain = renderKotText(input);
  if (!printerUrl) {
    const fallback = writeFallback(
      `kot-${input.order_number}-${input.time.replace(/\D/g, "")}`,
      plain,
    );
    return { success: false, reason: "no printer configured", fallbackPath: fallback };
  }
  const timeout = printerUrl.startsWith("cups://") ? 30_000 : TIMEOUT_MS;
  try {
    return await withTimeout(realPrintKOT(input, printerUrl), timeout, () => {
      const fallback = writeFallback(`kot-${input.order_number}`, plain);
      return {
        success: false,
        reason: `KOT printer timeout (${timeout / 1000}s)`,
        fallbackPath: fallback,
      };
    });
  } catch (e) {
    const fallback = writeFallback(`kot-${input.order_number}`, plain);
    return {
      success: false,
      reason: `KOT print error: ${e instanceof Error ? e.message : String(e)}`,
      fallbackPath: fallback,
    };
  }
}

async function realPrintKOT(input: KotInput, printerUrl: string): Promise<PrintResult> {
  let mod: any;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    mod = require("node-thermal-printer");
  } catch (e) {
    return { success: false, reason: "printer driver not installed" };
  }
  const transport = resolveTransport(printerUrl);
  const ThermalPrinter = mod.printer;
  const PrinterTypes = mod.types;
  const printer = new ThermalPrinter({
    type: resolveDialect() === "star" ? PrinterTypes.STAR : PrinterTypes.EPSON,
    interface: transport.ctorInterface,
    characterSet: PrinterTypes.CharacterSet?.[resolveCharset()] ?? undefined,
    width: input.width,
    options: { timeout: TIMEOUT_MS },
  });
  if (transport.kind === "direct") {
    const ok = await printer.isPrinterConnected();
    if (!ok) return { success: false, reason: `printer unreachable at ${printerUrl}` };
  }

  printer.alignCenter();
  printer.bold(true);
  printer.setTextDoubleHeight();
  printer.setTextDoubleWidth();
  // A void ticket leads with a loud CANCELLED header (not "KITCHEN") so the cook
  // immediately sees this order must NOT be prepared.
  printer.println(input.is_void ? "*** CANCELLED ***" : "KITCHEN");
  printer.setTextNormal();
  if (input.is_void) {
    printer.bold(true);
    printer.setTextDoubleHeight();
    printer.println("VOID — DO NOT PREPARE");
    printer.setTextNormal();
  } else if (input.is_additional) {
    // Loud banner so the cook knows this ticket ADDS to an order already fired
    // (same order number) rather than being a new order.
    printer.bold(true);
    printer.setTextDoubleHeight();
    printer.println("** ADDITIONAL ORDER **");
    printer.setTextNormal();
  }
  printer.bold(true);
  // Destination line: table for dine-in; else the cashier's reference/label;
  // else the order type. (Never lead with the hex order id.)
  printer.setTextSize(1, 1);
  const dest = input.table_name
    ? `TABLE ${input.table_name}`
    : input.reference?.trim() || input.order_type.replace("_", " ").toUpperCase();
  printer.println(dest);
  printer.setTextNormal();
  printer.bold(false);
  // Keep the order id on the ticket (small) so the SAME reference ties the
  // follow-up ticket back to the original — but it's no longer the headline.
  printer.println(`Order ${input.order_number}   ${input.time}`);
  if (input.reference && input.table_name) printer.println(`Ref: ${input.reference}`);
  if (input.covers) printer.println(`Covers: ${input.covers}`);
  printer.drawLine();
  printer.alignLeft();

  for (const it of input.items) {
    printer.bold(true);
    printer.setTextSize(1, 1);
    printer.println(`${qtyFmt(it.quantity)} x ${it.product_name}`);
    printer.setTextNormal();
    printer.bold(false);
    for (const m of it.modifiers ?? []) {
      printer.println(`   - ${m.name}`);
    }
    if (it.item_note) printer.println(`   ** ${it.item_note} **`);
    printer.newLine();
  }
  printer.drawLine();
  printer.cut();

  if (transport.kind !== "direct") {
    return flushBuffer(transport, printer.getBuffer());
  }
  try {
    await printer.execute();
    return { success: true };
  } catch (e) {
    return {
      success: false,
      reason: `KOT execute failed: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
}

// ---------------------------------------------------------------------------
// Consolidated folio bill (hotel stay) — one bill for the whole stay.
// ---------------------------------------------------------------------------

interface FolioBillInput {
  business_name: string;
  address?: string;
  contact?: string;
  ntn?: string;
  width: 48 | 32;
  is_fiscal?: boolean; // resort tenants → false (plain, no FBR block)
  folio: {
    folio_number: string;
    guest: { name: string; cnic: string; phone: string };
    room: { number: string; type: string } | null;
    check_in: string | null;
    check_out: string | null;
    nights: number;
    rooms?: { number: string; type: string; nights: number }[];
    days: {
      date: string;
      charges: {
        kind: string;
        room_number?: string | null;
        room_type?: string | null;
        items: {
          name: string;
          quantity: string;
          unit_price?: string;
          line_total: string;
          note?: string;
        }[];
        total: string;
      }[];
    }[];
    subtotal: string;
    tax_total: string;
    grand_total: string;
    paid_total: string;
    balance: string;
    // Cash settlement (optional): only set when the guest paid cash and gets
    // change back. Printed on the bill so the change is on the record.
    payment_method?: string;
    tendered?: string;
    change_given?: string;
  };
}

/** Print the consolidated stay bill. Non-fiscal text receipt (no FBR block);
 *  falls back to disk when no printer is configured so a bill is never lost. */
export async function printFolioBill(input: FolioBillInput): Promise<PrintResult> {
  const printerUrl = resolvePrinterInterface();
  const text = renderFolioText(input);
  const fileKey = `folio-${input.folio.folio_number}`;
  if (!printerUrl) {
    const fallback = writeFallback(fileKey, text);
    return { success: false, reason: "no printer configured", fallbackPath: fallback };
  }
  const timeout = printerUrl.startsWith("cups://") ? 30_000 : TIMEOUT_MS;
  try {
    return await withTimeout(realPrintFolio(text, input, printerUrl), timeout, () => {
      const fallback = writeFallback(fileKey, text);
      return {
        success: false,
        reason: `folio printer timeout (${timeout / 1000}s)`,
        fallbackPath: fallback,
      };
    });
  } catch (e) {
    const fallback = writeFallback(fileKey, text);
    return {
      success: false,
      reason: `folio print error: ${e instanceof Error ? e.message : String(e)}`,
      fallbackPath: fallback,
    };
  }
}

async function realPrintFolio(
  text: string,
  input: FolioBillInput,
  printerUrl: string,
): Promise<PrintResult> {
  let mod: any;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    mod = require("node-thermal-printer");
  } catch {
    return { success: false, reason: "printer driver not installed" };
  }
  const transport = resolveTransport(printerUrl);
  const ThermalPrinter = mod.printer;
  const PrinterTypes = mod.types;
  const printer = new ThermalPrinter({
    type: resolveDialect() === "star" ? PrinterTypes.STAR : PrinterTypes.EPSON,
    interface: transport.ctorInterface,
    characterSet: PrinterTypes.CharacterSet?.[resolveCharset()] ?? undefined,
    width: input.width,
    options: { timeout: TIMEOUT_MS },
  });
  // Only the "direct" transport can/should probe connectivity; cups + windows
  // flush the buffer through the OS spooler and have no live socket to probe.
  if (transport.kind === "direct") {
    const ok = await printer.isPrinterConnected();
    if (!ok) return { success: false, reason: `printer unreachable at ${printerUrl}` };
  }
  // Header: prefer the tenant LOGO (black thermal PNG) centered at the very top.
  // When present, it REPLACES the business-name/address/contact text block —
  // renderFolioText tags those lines so we can drop them here. If the logo asset
  // is missing, fall back to the bold business-name text banner.
  const bodyLines = text.split("\n");
  const logoPath = resolveReceiptLogoPath();
  let logoPrinted = false;
  if (logoPath) {
    try {
      printer.alignCenter();
      await printer.printImage(logoPath);
      // Resort name centered + bold directly UNDER the logo.
      try {
        printer.bold(true);
        printer.println(RECEIPT_LOGO_CAPTION);
        printer.bold(false);
      } catch {
        /* styling unsupported — plain text still prints */
      }
      printer.alignLeft();
      logoPrinted = true;
    } catch {
      logoPrinted = false; // printing the image failed → use text banner
    }
  }
  if (logoPrinted) {
    // Drop ALL header text lines (name/address/contact) so the logo stands
    // alone at the top.
    while (bodyLines.length && bodyLines[0].startsWith(HEADER_TAG)) bodyLines.shift();
  } else {
    // No logo — print the styled business-name banner, then drop just the
    // tagged NAME line so it isn't repeated (keep address/contact in the body).
    try {
      printer.alignCenter();
      printer.bold(true);
      printer.setTextSize(1, 1);
      printer.println(input.business_name.toUpperCase());
      printer.setTextNormal();
      printer.bold(false);
      printer.alignLeft();
    } catch {
      /* styling unsupported — body still has the name */
    }
    if (bodyLines.length && bodyLines[0].startsWith(HEADER_TAG)) bodyLines.shift();
  }
  // Strip the header tag from any remaining tagged lines before printing.
  for (const line of bodyLines)
    printer.println(line.startsWith(HEADER_TAG) ? line.slice(HEADER_TAG.length) : line);
  printer.cut();
  if (transport.kind !== "direct") return flushBuffer(transport, printer.getBuffer());
  try {
    await printer.execute();
    return { success: true };
  } catch (e) {
    return {
      success: false,
      reason: `folio execute failed: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
}

function renderFolioText(input: FolioBillInput): string {
  const W = input.width;
  const center = (s: string) =>
    s.length >= W ? s : " ".repeat(Math.floor((W - s.length) / 2)) + s;
  const rule = "-".repeat(W);
  const row = (k: string, v: string) => {
    const pad = Math.max(1, W - k.length - v.length);
    return k + " ".repeat(pad) + v;
  };
  const f = input.folio;
  const L: string[] = [];

  // Tag the header text lines so realPrintFolio can drop them when a logo is
  // printed at the top instead (see HEADER_TAG usage there).
  L.push(HEADER_TAG + center(input.business_name.toUpperCase()));
  if (input.address) L.push(HEADER_TAG + center(input.address));
  if (input.contact) L.push(HEADER_TAG + center(input.contact));
  L.push("");
  L.push(center("GUEST BILL"));
  L.push(rule);
  L.push(row("Folio", f.folio_number));
  L.push(row("Guest", f.guest.name));
  L.push(row("CNIC", f.guest.cnic));
  L.push(row("Phone", f.guest.phone));
  // Rooms: list all booked rooms (multi-room stay), else the single room.
  if (f.rooms && f.rooms.length > 0) {
    for (const r of f.rooms) {
      L.push(row("Room", `${r.number} (${r.type}) x ${r.nights}n`));
    }
  } else if (f.room) {
    L.push(row("Room", `${f.room.number} (${f.room.type})`));
  }
  if (f.check_in) L.push(row("Check-in", new Date(f.check_in).toLocaleString()));
  if (f.check_out) L.push(row("Check-out", new Date(f.check_out).toLocaleString()));
  L.push(row("Nights", String(f.nights)));
  L.push(rule);

  // Charges. A ROOM charge prints as ONE clean line (room title + amount) with a
  // subtle "N nights x rate" detail — no duplicated room number / product name.
  // A RESTAURANT charge prints a title then its items with per-item amounts.
  for (const day of f.days) {
    L.push(day.date);
    for (const ch of day.charges) {
      const isRoom = ch.kind === "room";
      if (isRoom) {
        const it = ch.items[0];
        // Room TYPE + number so the bill clearly says which room (e.g.
        // "VIP - Room 102"), not just a bare number.
        const title = (
          ch.room_type
            ? `${ch.room_type} - Room ${ch.room_number ?? ""}`
            : `Room ${ch.room_number ?? ""}`
        ).trim();
        L.push(row(title.slice(0, W - 12), money2(ch.total)));
        if (it) {
          const n = qtyFmt(it.quantity);
          // Tax-inclusive per-night rate = line_total / nights (advertised
          // price), not the tax-stripped unit_price.
          const qtyNum = Math.max(1, Number(it.quantity));
          const perNight = Number(it.line_total) / qtyNum;
          const unit = Number.isFinite(perNight) ? money2(perNight) : null;
          const nights = `${n} ${Number(it.quantity) === 1 ? "night" : "nights"}`;
          L.push(`   ${unit ? `${nights} x Rs ${unit}` : nights}`);
        }
      } else {
        const title = ch.room_number ? `Restaurant [Room ${ch.room_number}]` : "Restaurant";
        L.push(title);
        for (const it of ch.items) {
          const left = `  ${qtyFmt(it.quantity)} x ${it.name}`.slice(0, W - 10);
          L.push(row(left, money2(it.line_total)));
          if (it.note) L.push(`     ** ${it.note} **`);
        }
      }
    }
  }
  L.push(rule);
  L.push(row("Subtotal", money2(f.subtotal)));
  L.push(row("Tax", money2(f.tax_total)));
  L.push(row("GRAND TOTAL", moneyWhole(f.grand_total)));
  if (Number(f.paid_total) > 0) L.push(row("Paid", money2(f.paid_total)));
  // Cash tender/change, when the guest paid cash and got change back.
  if (f.tendered && Number(f.tendered) > 0) {
    L.push(row("Cash tendered", money2(f.tendered)));
    if (f.change_given && Number(f.change_given) > 0) {
      L.push(row("Change", money2(f.change_given)));
    }
  }
  if (Number(f.balance) !== 0) L.push(row("Balance", money2(f.balance)));
  L.push(rule);

  // Non-fiscal resort bill: a plain thank-you, no FBR block / pending notice.
  if (input.is_fiscal === false) {
    L.push(center("Thank you for staying with us!"));
  } else {
    L.push(center("Thank you!"));
  }
  L.push("");
  return L.join("\n");
}

function renderKotText(input: KotInput): string {
  const W = input.width;
  const center = (s: string) =>
    s.length >= W ? s : " ".repeat(Math.floor((W - s.length) / 2)) + s;
  const rule = "-".repeat(W);
  const lines: string[] = [center(input.is_void ? "*** CANCELLED ***" : "KITCHEN")];
  if (input.is_void) lines.push(center("VOID — DO NOT PREPARE"));
  else if (input.is_additional) lines.push(center("** ADDITIONAL ORDER **"));
  const dest = input.table_name
    ? `TABLE ${input.table_name}`
    : input.reference?.trim() || input.order_type.toUpperCase();
  lines.push(center(dest));
  lines.push(`Order ${input.order_number}   ${input.time}`);
  if (input.reference && input.table_name) lines.push(`Ref: ${input.reference}`);
  if (input.covers) lines.push(`Covers: ${input.covers}`);
  lines.push(rule);
  for (const it of input.items) {
    lines.push(`${qtyFmt(it.quantity)} x ${it.product_name}`);
    for (const m of it.modifiers ?? []) lines.push(`   - ${m.name}`);
    if (it.item_note) lines.push(`   ** ${it.item_note} **`);
  }
  lines.push(rule);
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Real printing via node-thermal-printer
// ---------------------------------------------------------------------------

async function realPrint(
  // The plain-text render is still used for the disk fallback (see printReceipt);
  // realPrint itself renders a STYLED header + the monospace body from `input`.
  _text: string,
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

  // macOS USB-class thermal printers (e.g. Black Copper / RONGTA) aren't a
  // /dev/serial or tcp interface — they're reachable only via a CUPS queue.
  // For "cups://<queue>" we build the ESC/POS buffer in memory and pipe it to
  // `lp -d <queue> -o raw`, bypassing node-thermal-printer's serial/tcp writer
  // (which can't address a CUPS queue). Everything else uses the native writer.
  // Pick the transport: cups (mac/Linux USB), windows (winspool RAW), or direct
  // (tcp/serial). cups + windows build the buffer here and flush via the OS.
  const transport = resolveTransport(printerUrl);

  const ThermalPrinter = mod.printer;
  const PrinterTypes = mod.types;
  const printer = new ThermalPrinter({
    type: resolveDialect() === "star" ? PrinterTypes.STAR : PrinterTypes.EPSON,
    // For cups/windows we only use the lib to BUILD the ESC/POS buffer
    // (getBuffer) and flush it ourselves — we never open this interface. The
    // lib's constructor still demands a valid interface string
    // ("printer:auto" throws "No driver set!"), so pass a harmless dummy tcp
    // address it never connects to. The direct path uses the real interface.
    interface: transport.ctorInterface,
    characterSet: PrinterTypes.CharacterSet?.[resolveCharset()] ?? undefined,
    width: input.width,
    options: { timeout: TIMEOUT_MS },
  });

  // Only "direct" can probe a live socket; cups + windows flush via the spooler.
  if (transport.kind === "direct") {
    const ok = await printer.isPrinterConnected();
    if (!ok) {
      console.error("[printer] not reachable at", printerUrl);
      return { success: false, reason: `printer unreachable at ${printerUrl}` };
    }
  }

  // ---- Styled header (matches the wireframe) ------------------------------
  // node-thermal-printer renders these ESC/POS attributes natively; the plain
  // `text` render (used for the disk fallback) can't, which is why the printed
  // receipt and the wireframe used to differ. Order: big bold business name,
  // address, bold "NTN #", larger+bold "Contact #", large bold "SALES INVOICE".
  printer.alignCenter();
  // Tenant logo at the top of the BILL (sales invoice). The KOT never prints a
  // logo. If the logo image prints, skip the big text business-name banner so
  // the logo stands alone; otherwise fall back to the text banner.
  let headerLogoPrinted = false;
  const receiptLogo = resolveReceiptLogoPath();
  if (receiptLogo) {
    try {
      await printer.printImage(receiptLogo);
      headerLogoPrinted = true;
    } catch {
      headerLogoPrinted = false; // image failed → text banner below
    }
  }
  if (!headerLogoPrinted) {
    printer.bold(true);
    printer.setTextDoubleHeight();
    printer.setTextDoubleWidth();
    printer.println(input.business_name.toUpperCase());
    printer.setTextNormal();
  }

  if (input.address) {
    printer.println(input.address);
  }

  printer.bold(true);
  printer.println(`NTN #: ${input.ntn}`);
  printer.bold(false);

  if (input.contact) {
    printer.bold(true);
    printer.setTextSize(1, 1); // a notch larger than body text
    printer.println(`Contact #: ${input.contact}`);
    printer.setTextNormal();
  }

  printer.bold(true);
  printer.setTextDoubleHeight();
  printer.setTextDoubleWidth();
  printer.println("SALES INVOICE");
  printer.setTextNormal();

  printer.bold(false);
  printer.println(input.branch_name);
  printer.drawLine();
  printer.alignLeft();

  // ---- Body (meta, items, totals, payments) — monospace for column align --
  for (const line of renderBodyText(input).split("\n")) {
    printer.println(line);
  }

  // FBR compliance block at the BOTTOM: FBR logo (LEFT) + QR (RIGHT) printed
  // SIDE-BY-SIDE as one composite bitmap (thermal printers can't natively put a
  // raster logo and a QR on the same band, so we composite them), then the
  // FBR-issued invoice number + verify line. The QR encodes EXACTLY the FBR
  // number (what Tax Asaan verifies). Only when the invoice has an FBR number.
  const isFiscal = input.is_fiscal !== false;
  const fbrNo = (input.invoice as { fbr_invoice_number?: string | null }).fbr_invoice_number;
  if (!isFiscal) {
    // Non-fiscal tenant (e.g. TDCP resort): no FBR block, no pending notice.
    // The "Thank you" footer in the body already closes the bill cleanly.
  } else if (fbrNo) {
    printer.alignCenter();
    // 48 cols ≈ 80mm ≈ 576 dots; 32 cols ≈ 58mm ≈ 384 dots.
    const dotWidth = input.width >= 48 ? 576 : 384;
    let stamped = false;
    try {
      const png = await buildFbrStampPng(fbrNo, dotWidth);
      if (png) {
        await printer.printImageBuffer(png);
        stamped = true;
      }
    } catch (e) {
      console.warn("[printer] FBR stamp composite failed:", e);
    }
    if (!stamped) {
      // Fallback: stacked logo + native QR if the composite couldn't be built.
      const logoPath = resolveFbrLogoPath();
      if (logoPath) {
        try {
          await printer.printImage(logoPath);
        } catch {
          /* ignore */
        }
      }
      try {
        await printer.printQR(fbrNo, { cellSize: 6 });
      } catch {
        /* ignore */
      }
    }
    printer.alignCenter();
    printer.bold(true);
    printer.println(fbrNo);
    printer.bold(false);
    printer.alignLeft();
  } else {
    // No FBR number yet (sale rung up offline). Print a clear, professional
    // notice instead of stopping abruptly after the totals — the receipt is a
    // complete customer bill; the FBR QR is added when it reprints after sync.
    printer.alignCenter();
    printer.println(FBR_PENDING_NOTICE);
    printer.alignLeft();
  }

  printer.cut();

  if (transport.kind !== "direct") {
    // Flush the assembled ESC/POS bytes via the OS spooler (cups or windows).
    return flushBuffer(transport, printer.getBuffer());
  }

  await printer.execute();
  return { success: true };
}

/**
 * Decide how to reach the configured printer. Three transports:
 *  - "cups"   → macOS/Linux USB-class printer, flushed via `lp -o raw`
 *  - "windows"→ Windows installed/USB printer (e.g. SPEED SP-200), flushed via
 *               the winspool RAW spooler (see win-print.ts)
 *  - "direct" → node-thermal-printer opens the tcp:// / serial interface itself
 *
 * For cups/windows we only use node-thermal-printer to BUILD the ESC/POS buffer
 * (getBuffer) and flush it ourselves — the lib's constructor still needs a
 * valid interface string, so those paths pass a harmless dummy tcp address it
 * never connects to.
 */
function resolveTransport(printerUrl: string): {
  kind: "cups" | "windows" | "direct";
  target: string;
  ctorInterface: string;
} {
  if (printerUrl.startsWith("cups://")) {
    return {
      kind: "cups",
      target: printerUrl.slice("cups://".length).replace(/\/+$/, ""),
      ctorInterface: "tcp://127.0.0.1:1",
    };
  }
  if (isWindowsInterface(printerUrl)) {
    return {
      kind: "windows",
      target: windowsPrinterName(printerUrl),
      ctorInterface: "tcp://127.0.0.1:1",
    };
  }
  return { kind: "direct", target: printerUrl, ctorInterface: printerUrl };
}

/** Flush an assembled ESC/POS buffer over the chosen non-direct transport. */
function flushBuffer(
  transport: { kind: "cups" | "windows" | "direct"; target: string },
  buffer: Buffer,
): Promise<PrintResult> {
  if (transport.kind === "cups") return printViaCups(buffer, transport.target);
  return printRawWindows(buffer, transport.target); // "windows"
}

/**
 * Send raw ESC/POS bytes to a macOS/Linux CUPS queue via `lp -d <queue> -o raw`.
 * Used for USB-class thermal printers on macOS that have no /dev or tcp address.
 */
function printViaCups(buffer: Buffer, queue: string): Promise<PrintResult> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { spawn } = require("node:child_process") as typeof import("node:child_process");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { existsSync } = require("node:fs") as typeof import("node:fs");
  // Electron GUI processes inherit a MINIMAL PATH (often missing /usr/bin), so
  // bare "lp" can fail to spawn (ENOENT). Use an absolute path to the CUPS lp.
  const lpBin =
    ["/usr/bin/lp", "/usr/local/bin/lp", "/opt/homebrew/bin/lp"].find((p) => existsSync(p)) ?? "lp";
  console.log(`[printer] CUPS print via ${lpBin} -d ${queue} (${buffer.length} bytes)`);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (r: PrintResult) => {
      if (!settled) {
        settled = true;
        resolve(r);
      }
    };
    let lp;
    try {
      lp = spawn(lpBin, ["-d", queue, "-o", "raw"], { stdio: ["pipe", "ignore", "pipe"] });
    } catch (e) {
      console.error("[printer] lp spawn threw:", e);
      return finish({ success: false, reason: `lp spawn failed: ${e}` });
    }
    let stderr = "";
    lp.stderr?.on("data", (d: Buffer) => {
      stderr += d.toString();
    });
    lp.on("error", (e: Error) => {
      console.error("[printer] lp error:", e.message);
      finish({ success: false, reason: `lp error: ${e.message}` });
    });
    lp.on("close", (code: number) => {
      if (code === 0) {
        console.log("[printer] CUPS job submitted OK");
        finish({ success: true });
      } else {
        console.error(`[printer] lp exited ${code}: ${stderr.trim()}`);
        finish({ success: false, reason: `lp exited ${code}: ${stderr.trim()}` });
      }
    });
    lp.stdin?.end(buffer);
  });
}

async function realOpenDrawer(printerUrl: string): Promise<{ success: boolean; reason?: string }> {
  let mod: any;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    mod = require("node-thermal-printer");
  } catch {
    return { success: false, reason: "printer driver not installed" };
  }
  const transport = resolveTransport(printerUrl);
  const ThermalPrinter = mod.printer;
  const PrinterTypes = mod.types;
  const printer = new ThermalPrinter({
    type: resolveDialect() === "star" ? PrinterTypes.STAR : PrinterTypes.EPSON,
    interface: transport.ctorInterface,
    options: { timeout: TIMEOUT_MS },
  });

  if (transport.kind === "direct") {
    const ok = await printer.isPrinterConnected();
    if (!ok) {
      return { success: false, reason: `printer unreachable at ${printerUrl}` };
    }
  }
  printer.openCashDrawer(); // ESC p 0 25 250 under the hood
  if (transport.kind !== "direct") {
    return flushBuffer(transport, printer.getBuffer());
  }
  await printer.execute();
  return { success: true };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function withTimeout<T>(promise: Promise<T>, ms: number, onTimeout: () => T): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((resolve) => setTimeout(() => resolve(onTimeout()), ms)),
  ]);
}

// ---------------------------------------------------------------------------
// Renderer (text-mode receipt body — same for real + fallback paths)
// ---------------------------------------------------------------------------

/**
 * Plain-text header (centered monospace). Used ONLY by the disk fallback —
 * the live print path renders a STYLED header (bold/large) in `realPrint`
 * instead, so the printed receipt matches the wireframe. Keep the two in sync.
 */
function renderHeaderText(input: ReceiptInput): string[] {
  const W = input.width;
  const center = (s: string) =>
    s.length >= W ? s : " ".repeat(Math.floor((W - s.length) / 2)) + s;
  const lines: string[] = [];
  lines.push(center(input.business_name.toUpperCase()));
  if (input.address) lines.push(center(input.address));
  lines.push(center(`NTN #: ${input.ntn}`));
  if (input.contact) lines.push(center(`Contact #: ${input.contact}`));
  lines.push(center("SALES INVOICE"));
  lines.push(center(input.branch_name));
  return lines;
}

/**
 * Receipt body BELOW the header: meta (invoice/date/buyer), items, totals,
 * payments, footer. Shared verbatim by the styled-print path and the disk
 * fallback so columns stay aligned. The FBR number is NOT here — it's printed
 * once at the bottom under the logo + QR.
 */
function renderBodyText(input: ReceiptInput): string {
  const W = input.width;
  const center = (s: string) =>
    s.length >= W ? s : " ".repeat(Math.floor((W - s.length) / 2)) + s;
  const rule = "-".repeat(W);
  const lines: string[] = [];

  lines.push(`Invoice: ${input.invoice.local_invoice_number}`);
  lines.push(`Date:    ${input.invoice.invoice_date}`);
  // Restaurant: order type + table for the customer's reference.
  if (input.order_type) {
    const ot = input.order_type.replace("_", " ");
    lines.push(`Order:   ${ot}${input.table_name ? ` — Table ${input.table_name}` : ""}`);
  }
  if (input.invoice.buyer_name) {
    lines.push(`Buyer:   ${input.invoice.buyer_name}`);
  }
  lines.push(rule);

  for (const it of input.items) {
    lines.push(it.product_name.slice(0, W));
    const left = `  ${qtyFmt(it.quantity)} x ${money2(it.unit_price)}`;
    // Show the PRE-TAX line amount (line_total − tax) so tax appears only once,
    // as the aggregate at the bottom. This makes the per-line amount match the
    // Subtotal and reads naturally (e.g. "1 x 1080.00 … 1080.00").
    const preTax = Number(it.line_total ?? 0) - Number(it.tax_amount ?? 0);
    const right = money2(preTax);
    const pad = Math.max(1, W - left.length - right.length);
    lines.push(left + " ".repeat(pad) + right);
    // Restaurant: show chosen modifiers under the line.
    const mods = (it as { modifiers?: { name: string }[] }).modifiers;
    if (mods && mods.length > 0) {
      lines.push(`    + ${mods.map((m) => m.name).join(", ")}`.slice(0, W));
    }
  }
  lines.push(rule);

  const totals: [string, string][] = [
    ["Subtotal", money2(input.invoice.subtotal)],
    ["Discount", money2(input.invoice.discount_total)],
    ["Tax", money2(input.invoice.tax_total)],
    ["TOTAL", moneyWhole(input.invoice.grand_total)],
    ["Tendered", money2(input.invoice.paid_total)],
    ["Change", money2(input.invoice.change_given)],
  ];
  for (const [k, v] of totals) {
    const pad = Math.max(1, W - k.length - v.length);
    lines.push(k + " ".repeat(pad) + v);
  }
  lines.push(rule);

  for (const p of input.payments) {
    const k = `Paid: ${p.payment_method}`;
    const v = money2(p.amount);
    const pad = Math.max(1, W - k.length - v.length);
    lines.push(k + " ".repeat(pad) + v);
  }
  lines.push(rule);

  // FBR-pending notice on the disk-fallback receipt too (offline sales) —
  // but NEVER for non-fiscal tenants (TDCP resort), who have no FBR at all.
  const isFiscal = input.is_fiscal !== false;
  const fbrNo = (input.invoice as { fbr_invoice_number?: string | null }).fbr_invoice_number;
  if (isFiscal && !fbrNo) {
    lines.push(center(FBR_PENDING_NOTICE));
    lines.push(rule);
  }

  lines.push(center("Thank you!"));
  lines.push("");
  return lines.join("\n");
}

/** Full plain-text receipt (header + body) — disk fallback only. */
function renderReceiptText(input: ReceiptInput): string {
  const rule = "-".repeat(input.width);
  return [...renderHeaderText(input), rule, renderBodyText(input)].join("\n");
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
