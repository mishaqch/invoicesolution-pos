/**
 * KOT relay — prints orders fired from a printer-less waiter tablet.
 *
 * A browser tablet cannot drive an ESC/POS printer, so a waiter fires the order
 * to the SERVER, and this branch terminal (which HAS the kitchen printer) picks
 * it up and prints it. The loop:
 *
 *   1. poll  GET  /api/restaurant/kds/unprinted/?branch=<id>
 *              → orders with fired, not-yet-printed food lines (rooms excluded
 *                server-side; only menu items reach the kitchen).
 *   2. print each via the existing printKOT (same path the cashier's own fire
 *      uses — banners, additional-order flag, etc.).
 *   3. ack   POST /api/restaurant/orders/<id>/mark-printed/ {item_ids:[...]}
 *              → server stamps kot_printed_at WHERE IS NULL (atomic), so a lost
 *                ack or two terminals racing print at most once, never twice.
 *
 * Safety / ordering:
 *  - We mark-printed ONLY after printKOT reports success. If printing fails we
 *    leave the lines unprinted so the next poll retries them (at-least-once).
 *  - The server's IS-NULL guard makes the ack idempotent, so retrying after a
 *    print that DID land (but whose ack was lost) simply no-ops — the order
 *    won't reprint because its lines are already stamped.
 *  - One order printed per tick at most avoids hammering the printer; the queue
 *    drains over subsequent ticks.
 *
 * This runs in the MAIN process (mirrors startReachabilityMonitor): only the
 * main process has the printer + the persisted access token in kv_meta.
 */

import { getMeta } from "./db/client";
import { deviceFingerprint, getPairedIdentity, isPaired } from "./pairing";
import { printKOT } from "./printer";

const POLL_MS = 8_000;

let relayTimer: ReturnType<typeof setInterval> | null = null;
let inFlight = false;

interface UnprintedItem {
  product_name: string;
  quantity: string | number;
  modifiers?: { name: string }[];
  item_note?: string | null;
}

interface UnprintedOrder {
  id: string;
  order_number: string;
  order_type: string;
  table_name?: string | null;
  covers?: number | null;
  reference?: string | null;
  is_additional?: boolean;
  items: UnprintedItem[];
  item_ids: string[];
}

function accessToken(): string | null {
  return getMeta("access_token");
}

/** Auth headers for a relay call. The relay authenticates by PAIRED DEVICE
 *  (terminal_id + device_fingerprint sent in the request), so it works even when
 *  no cashier is logged into this till — kitchen printing must not depend on a
 *  login. A bearer token is attached too when present (harmless), but is not
 *  required. */
function authHeaders(): Record<string, string> {
  const token = accessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  ms: number,
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

function hhmm(d: Date = new Date()): string {
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

async function tick(base: string): Promise<void> {
  if (inFlight) return; // never overlap ticks
  if (!isPaired()) return; // no branch identity yet — can't authenticate as a device
  const identity = getPairedIdentity();
  if (!identity) return;
  const { branchId, terminalId } = identity;
  const fp = deviceFingerprint();
  // Device credentials authenticate the relay independently of any cashier
  // login. Sent as query params on the GET, in the body on the POST.
  const dev = `terminal_id=${encodeURIComponent(terminalId)}&device_fingerprint=${encodeURIComponent(fp)}`;

  inFlight = true;
  try {
    const res = await fetchWithTimeout(
      `${base}/api/restaurant/kds/unprinted/?branch=${encodeURIComponent(branchId)}&${dev}`,
      { headers: authHeaders() },
      8_000,
    );
    if (!res.ok) return; // transient error — try again next tick
    const data = (await res.json()) as { orders?: UnprintedOrder[] };
    const orders = data.orders ?? [];
    if (orders.length === 0) return;

    // Print ONE order per tick — keeps the printer sane and lets each ack land
    // before the next order is pulled.
    const order = orders[0]!;
    if (!order.items.length) return;

    const printed = await printKOT({
      order_number: order.order_number,
      order_type: order.order_type || "dine_in",
      table_name: order.table_name ?? null,
      covers: order.covers ?? null,
      time: hhmm(),
      items: order.items,
      width: 48,
      reference: order.reference ?? null,
      is_additional: !!order.is_additional,
    });
    if (!printed.success) {
      // Leave it unprinted; next tick retries. (printKOT already logged why.)
      console.warn("[kot-relay] print failed for", order.order_number, printed.reason);
      return;
    }

    // Ack only after a successful print. IS-NULL guard on the server makes this
    // idempotent, so a lost ack simply reprints nothing next time.
    await fetchWithTimeout(
      `${base}/api/restaurant/orders/${order.id}/mark-printed/`,
      {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          item_ids: order.item_ids,
          terminal_id: terminalId,
          device_fingerprint: fp,
        }),
      },
      8_000,
    );
  } catch (err) {
    // Network blip / timeout — the loop just tries again on the next tick.
    console.warn("[kot-relay] tick error:", err instanceof Error ? err.message : err);
  } finally {
    inFlight = false;
  }
}

export function startKotRelay(apiBase: string): void {
  if (relayTimer) return;
  const base = apiBase.replace(/\/$/, "");
  relayTimer = setInterval(() => void tick(base), POLL_MS);
}

export function stopKotRelay(): void {
  if (relayTimer) {
    clearInterval(relayTimer);
    relayTimer = null;
  }
}
