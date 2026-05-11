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
