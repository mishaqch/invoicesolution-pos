import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useModules } from "./hooks";

/**
 * Route guard for DI-API-only FBR pages (Setup wizard, Scenarios).
 *
 * Tenants on the FBR IMS / SDC Fiscalization service have no PRAL Bearer token
 * and no sandbox scenarios, so these pages are irrelevant to them — redirect
 * to the FBR dashboard. Waits for the modules query so we don't bounce a
 * DI-API tenant on first paint.
 */
export function RequireDiApi({ children }: { children: ReactNode }) {
  const { data, isLoading } = useModules();
  if (isLoading || !data) return null;
  if (data.fbr_connection_type === "ims_sdc") {
    return <Navigate to="/fbr" replace />;
  }
  return <>{children}</>;
}
