import { type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useSessionStore } from "@/stores/session";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const access = useSessionStore((s) => s.access);
  const location = useLocation();
  if (!access) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
