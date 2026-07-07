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
export interface FolioBillCharge {
  charge_id: string;
  kind: string;
  invoice_number: string;
  room_number: string | null;
  can_remove: boolean;
  items: FolioBillItem[];
  subtotal: string;
  tax: string;
  total: string;
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
  guest: { name: string; cnic: string; phone: string; email: string; address: string };
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
  return api<{ results: Room[] } | Room[]>(`/hotel/rooms/${q ? `?${q}` : ""}`).then(
    (d) => (Array.isArray(d) ? d : d.results),
  );
}

export function listOpenFolios() {
  return api<{ results: FolioRow[] } | FolioRow[]>(`/hotel/folios/?status=open`).then(
    (d) => (Array.isArray(d) ? d : d.results),
  );
}

export function openStay(body: OpenStayBody) {
  return api<FolioBill>(`/hotel/folios/`, { method: "POST", body: JSON.stringify(body) });
}

export function getFolio(id: string) {
  return api<FolioBill>(`/hotel/folios/${id}/`);
}

export function addCharge(id: string, cart_lines: ChargeLine[], kind = "restaurant", room?: string | null) {
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
