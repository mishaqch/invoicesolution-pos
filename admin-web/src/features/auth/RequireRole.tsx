/**
 * Route guard by ROLE. Wrap a <Route> element whose page should only render
 * for certain tenant roles (e.g. Users management is owner/manager only). If
 * the current user's role isn't allowed, redirect to the dashboard rather than
 * 404 — the server already enforces the real permission (HasRolePerm); this is
 * the UX layer.
 */

import { Navigate } from "react-router-dom";

import type { Role } from "@pos/shared/types";
import { useAuthStore } from "@/stores/auth";

interface Props {
  anyOf: Role[];
  children: React.ReactNode;
}

export function RequireRole({ anyOf, children }: Props) {
  const role = useAuthStore((s) => s.role);
  if (!role || !anyOf.includes(role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
