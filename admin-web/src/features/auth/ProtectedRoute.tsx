import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuthStore } from "@/stores/auth";

/**
 * Gates everything inside the AdminShell. Three guard conditions:
 *
 *   1. No access token → punt to /login.
 *   2. Stored tenant is null → the persisted session is for a platform-
 *      staff user (or a tenant-less user) who cannot use this surface.
 *      Clear the session and punt to /login. The login form refuses
 *      to re-establish such sessions, so this is one-time recovery for
 *      browsers that still have the old JWT in localStorage from before
 *      we shipped the platform-staff check.
 *
 * Future condition (Phase 9): if /me/modules/ returns 403 because the
 * tenant was suspended, log out with a friendlier message.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const access = useAuthStore((s) => s.access);
  const tenant = useAuthStore((s) => s.tenant);
  const logout = useAuthStore((s) => s.logout);
  const location = useLocation();

  // Stale platform-staff JWT in localStorage from a previous session.
  // Clear it so the redirect-to-login lands on a clean slate.
  useEffect(() => {
    if (access && !tenant) {
      logout();
    }
  }, [access, tenant, logout]);

  if (!access || !tenant) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
