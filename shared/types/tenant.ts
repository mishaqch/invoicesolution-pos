import type { Role } from "./user";

export type SubscriptionStatus =
  | "trial"
  | "active"
  | "past_due"
  | "suspended"
  | "cancelled";

export interface Tenant {
  id: string;
  business_name: string;
  ntn: string;
  subscription_status: SubscriptionStatus;
  logo_url: string | null;
}

export interface TenantMembership {
  id: string;
  tenant_id: string;
  user_id: string;
  role: Role;
  branch_ids: string[];
  is_active: boolean;
}
