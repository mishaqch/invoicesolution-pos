/**
 * Hotel / guest-folio API client (terminal side).
 *
 * Online API (not local-SQLite-mirrored): a stay lives on the server and is
 * recalled by the terminal. Charges still flow through the normal offline-safe
 * checkout path under the hood — the folio endpoints just group them. For the
 * resort use-case the reception counter is generally online; if a charge is
 * added offline it errors gracefully and the cashier retries.
 */
import { api } from "@/lib/api";

export interface Room {
  id: string;
  branch: string;
  room_number: string;
  room_type: string;
  nightly_base: string;
  nightly_tax: string;
  nightly_total: string;
  status: "available" | "occupied" | "maintenance";
  is_active: boolean;
}

export interface FolioRow {
  id: string;
  folio_number: string;
  guest_name: string;
  guest_phone: string;
  room: string | null;
  room_number: string | null;
  room_type: string | null;
  // All rooms booked on this stay (multi-room). Falls back to the primary room.
  rooms?: { number: string; type: string }[];
  check_in: string;
  expected_check_out: string | null;
  check_out: string | null;
  nights: number;
  status: "open" | "closed" | "cancelled";
  created_at: string;
}

export interface FolioBillItem {
  id: string;
  name: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
  line_total: string;
  note: string;
}
export interface FolioChargeInvoice {
  id: string;
  client_uuid: string;
  local_invoice_number: string;
  status: string;
  invoice_date: string | null;
  branch_id: string;
  terminal_id: string | null;
  cashier_id: string | null;
  buyer_name: string | null;
  subtotal: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  fbr_invoice_number: string | null;
  fbr_qr_payload: string | null;
  created_at: string | null;
  notes: string | null;
}
export interface FolioBillCharge {
  charge_id: string;
  kind: string;
  invoice_number: string;
  room_number: string | null;
  room_type: string | null;
  can_remove: boolean;
  items: FolioBillItem[];
  subtotal: string;
  tax: string;
  total: string;
  // The underlying server invoice, for mirroring into local SQLite.
  invoice?: FolioChargeInvoice;
}
export interface FolioBillRoom {
  id: string;
  number: string;
  type: string;
  nights: number;
  nightly_total: string;
  check_in: string | null;
  expected_check_out: string | null;
}
export interface FolioBill {
  id: string;
  folio_number: string;
  status: string;
  guest: {
    name: string;
    cnic: string;
    phone: string;
    email: string;
    address: string;
    partner_name?: string;
    partner_cnic?: string;
  };
  room: { number: string; type: string; nightly_total: string } | null;
  rooms: FolioBillRoom[];
  check_in: string | null;
  check_out: string | null;
  expected_check_out: string | null;
  nights: number;
  days: { date: string; charges: FolioBillCharge[] }[];
  subtotal: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  balance: string;
}

export interface OpenStayBody {
  room?: string;
  rooms?: string[];
  guest_name: string;
  guest_cnic: string;
  guest_phone: string;
  guest_email?: string;
  guest_address?: string;
  partner_name?: string;
  partner_cnic?: string;
  check_in?: string;
  expected_check_out?: string;
  notes?: string;
  terminal?: string;
}

export interface ChargeLine {
  product: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  is_taxable: boolean;
  discount_amount?: string;
  item_note?: string | null;
  modifiers?: { name: string; price: string }[];
}

export function listRooms(params: { status?: string } = {}) {
  const q = new URLSearchParams(params as Record<string, string>).toString();
  return api<{ results: Room[] } | Room[]>(`/hotel/rooms/${q ? `?${q}` : ""}`).then((d) =>
    Array.isArray(d) ? d : d.results,
  );
}

export function listOpenFolios() {
  return api<{ results: FolioRow[] } | FolioRow[]>(`/hotel/folios/?status=open`).then((d) =>
    Array.isArray(d) ? d : d.results,
  );
}

export function openStay(body: OpenStayBody) {
  return api<FolioBill>(`/hotel/folios/`, { method: "POST", body: JSON.stringify(body) });
}

export function getFolio(id: string) {
  return api<FolioBill>(`/hotel/folios/${id}/`);
}

// A server invoice row (subset of the InvoiceViewSet payload) used to mirror
// server-created invoices (e.g. folio charges) into local SQLite for display.
export interface ServerInvoiceRow {
  id: string;
  client_uuid: string;
  local_invoice_number: string;
  status: string;
  invoice_date: string | null;
  branch: string;
  terminal: string | null;
  cashier: string | null;
  buyer_name: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  fbr_invoice_number: string | null;
  fbr_qr_payload: string | null;
  created_at: string | null;
  notes: string | null;
  items?: {
    id: string;
    product_name: string;
    quantity: string;
    unit_price: string;
    tax_amount: string;
    line_total: string;
    hs_code?: string | null;
  }[];
}

/** List this terminal's server invoices (for online merge into Today's list).
 *  held=false is CRITICAL: Today's invoices must show only real (charged) sales,
 *  never open/held restaurant orders. Without this filter the mirror pulled held
 *  orders and cached them locally as is_held=0, so parked/open orders wrongly
 *  appeared as today's sales. */
export function listServerInvoices(params: { terminal?: string; limit?: number } = {}) {
  const q = new URLSearchParams();
  if (params.terminal) q.set("terminal", params.terminal);
  q.set("held", "false");
  q.set("page_size", String(params.limit ?? 200));
  return api<{ results: ServerInvoiceRow[] } | ServerInvoiceRow[]>(
    `/sales/invoices/?${q.toString()}`,
  ).then((d) => (Array.isArray(d) ? d : d.results));
}

/** Mirror a batch of server invoice rows into local SQLite (display cache). */
export async function mirrorServerInvoices(rows: ServerInvoiceRow[]): Promise<void> {
  const persist = (
    window as unknown as {
      api?: { sales?: { persistServerInvoice?: (a: unknown) => Promise<unknown> } };
    }
  ).api?.sales?.persistServerInvoice;
  if (!persist) return;
  for (const inv of rows) {
    try {
      await persist({
        invoice: {
          id: inv.id,
          client_uuid: inv.client_uuid,
          local_invoice_number: inv.local_invoice_number,
          status: inv.status,
          invoice_date: inv.invoice_date ?? (inv.created_at ?? "").slice(0, 10),
          customer_id: null,
          buyer_name: inv.buyer_name,
          buyer_phone: null,
          buyer_ntn_cnic: null,
          buyer_registration_type: null,
          branch_id: inv.branch,
          terminal_id: inv.terminal ?? "",
          cashier_id: inv.cashier ?? "",
          cash_session_id: null,
          subtotal: inv.subtotal,
          discount_total: inv.discount_total,
          tax_total: inv.tax_total,
          grand_total: inv.grand_total,
          paid_total: inv.paid_total,
          change_given: "0",
          notes: inv.notes,
          fbr_invoice_number: inv.fbr_invoice_number,
          fbr_qr_payload: inv.fbr_qr_payload,
          created_at: inv.created_at,
        },
        items: (inv.items ?? []).map((it, i) => ({
          id: it.id,
          invoice_id: inv.id,
          line_number: i + 1,
          product_id: "",
          product_name: it.product_name,
          product_sku: "",
          uom_code: "",
          hs_code: it.hs_code ?? null,
          quantity: it.quantity,
          unit_price: it.unit_price,
          discount_pct: "0",
          discount_amount: "0",
          tax_rate: "0",
          tax_amount: it.tax_amount,
          line_total: it.line_total,
          notes: null,
        })),
        payments: [],
      });
    } catch {
      // best-effort
    }
  }
}

/**
 * Mirror every charge invoice on a folio bill into the terminal's local SQLite,
 * so hotel folio charges show up in "Today's invoices" and reprint offline.
 * These invoices are created SERVER-side, so we only cache them (no sync
 * enqueue). Best-effort: failures are swallowed — the server remains the source
 * of truth and the folio flow itself is unaffected.
 */
export async function mirrorFolioInvoices(bill: FolioBill): Promise<void> {
  const persist = (
    window as unknown as {
      api?: { sales?: { persistServerInvoice?: (a: unknown) => Promise<unknown> } };
    }
  ).api?.sales?.persistServerInvoice;
  if (!persist) return; // older preload — nothing to do
  for (const day of bill.days ?? []) {
    for (const ch of day.charges ?? []) {
      const inv = ch.invoice;
      if (!inv) continue;
      try {
        await persist({
          invoice: {
            id: inv.id,
            client_uuid: inv.client_uuid,
            local_invoice_number: inv.local_invoice_number,
            status: inv.status,
            invoice_date: inv.invoice_date ?? (inv.created_at ?? "").slice(0, 10),
            customer_id: null,
            buyer_name: inv.buyer_name,
            buyer_phone: null,
            buyer_ntn_cnic: null,
            buyer_registration_type: null,
            branch_id: inv.branch_id,
            terminal_id: inv.terminal_id ?? "",
            cashier_id: inv.cashier_id ?? "",
            cash_session_id: null,
            subtotal: inv.subtotal,
            discount_total: "0",
            tax_total: inv.tax_total,
            grand_total: inv.grand_total,
            paid_total: inv.paid_total,
            change_given: "0",
            notes: inv.notes,
            fbr_invoice_number: inv.fbr_invoice_number,
            fbr_qr_payload: inv.fbr_qr_payload,
            created_at: inv.created_at,
          },
          items: ch.items.map((it, i) => ({
            id: it.id,
            invoice_id: inv.id,
            line_number: i + 1,
            product_id: "",
            product_name: it.name,
            product_sku: "",
            uom_code: "",
            hs_code: null,
            quantity: it.quantity,
            unit_price: it.unit_price,
            discount_pct: "0",
            discount_amount: "0",
            tax_rate: "0",
            tax_amount: it.tax_amount,
            line_total: it.line_total,
            notes: it.note || null,
          })),
          payments: [],
        });
      } catch {
        // best-effort cache; ignore
      }
    }
  }
}

export function addCharge(
  id: string,
  cart_lines: ChargeLine[],
  kind = "restaurant",
  room?: string | null,
) {
  return api<FolioBill>(`/hotel/folios/${id}/charges/`, {
    method: "POST",
    body: JSON.stringify({ cart_lines, kind, room: room ?? undefined }),
  });
}

export function checkoutFolio(id: string, payments: { payment_method: string; amount: string }[]) {
  return api<FolioBill>(`/hotel/folios/${id}/checkout/`, {
    method: "POST",
    body: JSON.stringify({ payments }),
  });
}

/** Void one item on a charge (open folio). Returns the updated bill. */
export function removeItem(folioId: string, chargeId: string, itemId: string) {
  return api<FolioBill>(`/hotel/folios/${folioId}/charges/${chargeId}/items/${itemId}/`, {
    method: "DELETE",
  });
}

/** Void a whole charge entry (open folio). Returns the updated bill. */
export function removeCharge(folioId: string, chargeId: string) {
  return api<FolioBill>(`/hotel/folios/${folioId}/charges/${chargeId}/`, {
    method: "DELETE",
  });
}

export interface UpdateStayBody {
  guest_name?: string;
  guest_cnic?: string;
  guest_phone?: string;
  guest_email?: string;
  guest_address?: string;
  partner_name?: string;
  partner_cnic?: string;
  notes?: string;
  check_in?: string;
  expected_check_out?: string | null;
  terminal?: string;
}

/** Edit an open stay's guest details and/or dates. Returns the updated bill. */
export function updateStay(id: string, body: UpdateStayBody) {
  return api<FolioBill>(`/hotel/folios/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Add another room to an open stay (same guest). Returns the updated bill. */
export function addRoom(
  id: string,
  room: string,
  opts: { check_in?: string; expected_check_out?: string | null } = {},
) {
  return api<FolioBill>(`/hotel/folios/${id}/rooms/`, {
    method: "POST",
    body: JSON.stringify({ room, ...opts }),
  });
}

/** Remove a room from an open multi-room stay (manager/owner). Updated bill. */
export function removeRoom(folioId: string, roomId: string) {
  return api<FolioBill>(`/hotel/folios/${folioId}/rooms/${roomId}/`, {
    method: "DELETE",
  });
}

/** Cancel a whole open stay (manager/owner). Voids charges, frees rooms. */
export function cancelStay(id: string, reason = "") {
  return api<FolioBill>(`/hotel/folios/${id}/cancel/`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
