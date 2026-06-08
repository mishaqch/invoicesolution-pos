import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useModules, type Vertical } from "./hooks";

/**
 * Route guard for vertical-specific pages (e.g. pharmacy-only Expiry,
 * Suppliers, batch management).
 *
 * If the current tenant's vertical doesn't match `vertical`, redirect to the
 * dashboard. Waits for the modules query so we don't bounce a matching tenant
 * on first paint. Pair with sidebar gating so the link is also hidden.
 */
export function RequireVertical({
  vertical,
  children,
}: {
  vertical: Vertical;
  children: ReactNode;
}) {
  const { data, isLoading } = useModules();
  if (isLoading || !data) return null;
  if (data.vertical !== vertical) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
