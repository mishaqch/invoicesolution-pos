/**
 * Per-tenant module gates set by super-admin.
 *
 * `useModules()` fetches /api/me/modules/ on app boot and caches it so
 * the sidebar and route guards have synchronous access. Refetch is
 * cheap (the endpoint is tiny) but we set a long staleTime — module
 * config changes via Django admin are rare events, not per-click.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface ModuleCatalogEntry {
  key: string;
  label: string;
  group: string;
  description: string;
  forced: boolean;
}

export interface ModulesPayload {
  catalog: ModuleCatalogEntry[];
  enabled: string[];
}

/** Module keys (mirrors apps/tenants/modules.py — keep in sync). */
export type ModuleKey =
  | "sales"
  | "fbr"
  | "customers"
  | "branches"
  | "terminals"
  | "inventory"
  | "returns"
  | "debit_credit_notes"
  | "manual_amendments"
  | "payments_advanced"
  | "customer_display"
  | "hardware"
  | "reports_basic"
  | "reports_advanced"
  | "audit_log";

export function useModules() {
  return useQuery({
    queryKey: ["me-modules"],
    queryFn: () => api<ModulesPayload>("/me/modules/"),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/** Returns true if a module is enabled for the current tenant.
 *  Returns true while the modules query is loading so we don't flicker
 *  the sidebar (better to show too much briefly than too little). */
export function useIsModuleEnabled(key: ModuleKey): boolean {
  const { data, isLoading } = useModules();
  if (isLoading || !data) return true;
  return data.enabled.includes(key);
}
