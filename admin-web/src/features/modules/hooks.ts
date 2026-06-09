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

export type FbrConnectionType = "di_api" | "ims_sdc";
export type BusinessMode = "pos" | "digital_invoicing" | "both";
/** The KIND of shop — decides which sections the UI surfaces (pharmacy gets
 *  batch/expiry/supplier tools; restaurant gets tables/menu/kitchen). Mirrors
 *  apps/tenants/business_mode.VERTICALS. */
export type Vertical = "grocery" | "pharmacy" | "restaurant";

export interface ModulesPayload {
  catalog: ModuleCatalogEntry[];
  enabled: string[];
  business_mode: BusinessMode;
  // How this tenant reaches FBR — drives mode-aware FBR/Branches UI:
  //   di_api  -> PRAL token setup + sandbox scenarios
  //   ims_sdc -> IMS Fiscalization service: POS ID only, no token, no scenarios
  fbr_connection_type: FbrConnectionType;
  // Presentation vertical — grocery vs pharmacy. UI-only; does not gate access.
  vertical: Vertical;
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
  | "restaurant"
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

/** The tenant's FBR connection type ("di_api" until loaded). Drives whether
 *  DI-API-only controls (PRAL token setup, sandbox scenarios, per-branch
 *  Bearer token) are shown, vs the IMS/SDC view (POS ID only). */
export function useFbrConnectionType(): FbrConnectionType {
  const { data } = useModules();
  return data?.fbr_connection_type ?? "di_api";
}

/** True when the tenant uses the FBR IMS / SDC Fiscalization service (so the
 *  DI-API token + scenarios UI is irrelevant and should be hidden). */
export function useIsImsSdc(): boolean {
  return useFbrConnectionType() === "ims_sdc";
}

/** The tenant's vertical ("grocery" until loaded). Drives whether pharmacy-only
 *  sections (batch/expiry management, expiry alerts, suppliers) are shown. */
export function useVertical(): Vertical {
  const { data } = useModules();
  return data?.vertical ?? "grocery";
}

/** True when the tenant is a pharmacy (so batch/expiry/supplier UI is shown). */
export function useIsPharmacy(): boolean {
  return useVertical() === "pharmacy";
}

/** True when the tenant is a restaurant (so tables/menu/kitchen UI is shown). */
export function useIsRestaurant(): boolean {
  return useVertical() === "restaurant";
}
