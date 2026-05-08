export type Role = "owner" | "manager" | "cashier" | "accountant" | "auditor";

export type Language = "en" | "ur";

export interface User {
  id: string;
  email: string;
  full_name: string;
  preferred_language: Language;
  is_staff: boolean;
}
