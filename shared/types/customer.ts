export type CustomerRegistrationType = "registered" | "unregistered";

export interface CustomerGroup {
  id: string;
  name: string;
  default_discount_pct: string;
}

export interface Customer {
  id: string;
  group: string | null;
  customer_code: string | null;
  name: string;
  phone: string | null;
  email: string | null;
  cnic: string | null;
  ntn: string | null;
  registration_type: CustomerRegistrationType;
  province: string | null;
  address: string;
  store_credit: string;
  current_balance: string;
  loyalty_points: number;
  is_active: boolean;
}

export interface CashSession {
  id: string;
  branch: string;
  terminal: string;
  cashier: string;
  opened_at: string;
  opened_with_amount: string;
  closed_at: string | null;
  closed_with_amount: string | null;
  expected_amount: string | null;
  variance: string | null;
  variance_reason: string;
  total_sales: string;
  cash_in: string;
  cash_out: string;
  status: "open" | "closed";
}
