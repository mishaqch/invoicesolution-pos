import type { Role } from "./user";

export type SubscriptionStatus =
  | "trial"
  | "active"
  | "past_due"
  | "suspended"
  | "cancelled";

/** The KIND of shop — grocery vs pharmacy vs restaurant. UI-only presentation flag. */
export type Vertical = "grocery" | "pharmacy" | "restaurant";

/** HOW the tenant reaches a tax authority. "none" = non-fiscal (no FBR/PRA). */
export type FbrConnectionType = "di_api" | "ims_sdc" | "none";

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
  /** Fiscal connection. "none" → plain non-fiscal receipts (no FBR QR/number). */
  fbr_connection_type?: FbrConnectionType;
  /** Enabled modules. The `hotel` module surfaces the Stays/Rooms folio flow. */
  modules_enabled?: string[];
}

export interface TenantMembership {
  id: string;
  tenant_id: string;
  user_id: string;
  role: Role;
  branch_ids: string[];
  is_active: boolean;
}
