export type InvoiceStatus =
  | "pending_sync" | "submitted" | "valid" | "failed"
  | "edited" | "partially_edited"
  | "cancelled" | "partially_cancelled" | "partially_edited_and_cancelled"
  | "finalized";

export interface SaleItem {
  id: string;
  line_number: number;
  product: string;
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
  is_edited: boolean;
  is_cancelled: boolean;
  edit_count: number;
  created_at: string;
}

export type PaymentMethod =
  | "cash" | "card_credit" | "card_debit"
  | "easypaisa" | "jazzcash" | "raast"
  | "bank_transfer" | "store_credit" | "cheque";

export interface Payment {
  id: string;
  invoice: string | null;
  customer: string | null;
  payment_method: PaymentMethod;
  amount: string;
  status: "pending" | "completed" | "failed" | "refunded";
  created_at: string;
}

export interface Invoice {
  id: string;
  branch: string;
  terminal: string;
  cashier: string;
  customer: string | null;
  local_invoice_number: string;
  fbr_invoice_number: string | null;
  invoice_type: "sale" | "debit_note" | "credit_note";
  invoice_date: string;
  buyer_name: string | null;
  buyer_phone: string | null;
  buyer_ntn_cnic: string | null;
  buyer_registration_type: "Registered" | "Unregistered";
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  change_given: string;
  status: InvoiceStatus;
  edit_deadline_at: string | null;
  client_uuid: string;
  notes: string | null;
  is_held: boolean;
  held_label: string | null;
  items: SaleItem[];
  payments: Payment[];
  created_at: string;
  updated_at: string;
}
