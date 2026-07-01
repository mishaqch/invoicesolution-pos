/** Hotel / resort — rooms + multi-day guest folios. */

export type RoomStatus = "available" | "occupied" | "maintenance";
export type FolioStatus = "open" | "closed" | "cancelled";

export interface Room {
  id: string;
  branch: string;
  room_number: string;
  room_type: string;
  /** Per-night base + FIXED tax amount (not %). */
  nightly_base: string;
  nightly_tax: string;
  nightly_total: string;
  product: string | null;
  display_order: number;
  status: RoomStatus;
  is_active: boolean;
}

/** Light row for the folios list. */
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
  status: FolioStatus;
  created_at: string;
}

/** Consolidated bill (folio detail) — every charge grouped by day + totals. */
export interface FolioBillItem {
  name: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
  line_total: string;
  note: string;
}
export interface FolioBillCharge {
  kind: string;
  invoice_number: string;
  items: FolioBillItem[];
  subtotal: string;
  tax: string;
  total: string;
}
export interface FolioBill {
  id: string;
  folio_number: string;
  status: FolioStatus;
  guest: { name: string; cnic: string; phone: string; email: string; address: string };
  room: { number: string; type: string; nightly_total: string } | null;
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
