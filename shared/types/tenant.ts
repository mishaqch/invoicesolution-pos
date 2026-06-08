import type { Role } from "./user";

export type SubscriptionStatus =
  | "trial"
  | "active"
  | "past_due"
  | "suspended"
  | "cancelled";

/** The KIND of shop — grocery vs pharmacy. UI-only presentation flag. */
export type Vertical = "grocery" | "pharmacy";

export interface Tenant {
  id: string;
  business_name: string;
  ntn: string;
  subscription_status: SubscriptionStatus;
  logo_url: string | null;
  /** Business address + contact number — printed on the POS receipt header. */
  address: string | null;
  phone: string | null;
  /** Shop vertical (grocery/pharmacy) — drives pharmacy-only terminal UI. */
  vertical: Vertical;
}

export interface TenantMembership {
  id: string;
  tenant_id: string;
  user_id: string;
  role: Role;
  branch_ids: string[];
  is_active: boolean;
}
