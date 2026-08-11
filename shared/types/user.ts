export type Role = "owner" | "manager" | "cashier" | "accountant" | "auditor";

export type Language = "en" | "ur";

export interface User {
  id: string;
  email: string;
  full_name: string;
  preferred_language: Language;
  is_staff: boolean;
  /** True when the user is a platform / super-admin operator (works
   *  for the SaaS company, not for a tenant). Such users have no
   *  tenant membership and cannot use the React tenant admin. */
  is_platform_staff: boolean;
}

/** A tenant staff member — the flattened TenantMembership shown in the
 *  Users/Cashiers admin. `id` is the MEMBERSHIP id. */
export interface StaffMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  /** Branches this user can work at. Empty = all branches. */
  branch_ids: string[];
  is_active: boolean;
  /** Whether a terminal PIN is set (the PIN itself is never returned). */
  has_pin: boolean;
  last_login: string | null;
  preferred_language: Language;
  created_at: string;
}

/** Lightweight branch option for the staff branch-assign multi-select. */
export interface BranchOption {
  id: string;
  name: string;
  code: string;
}
