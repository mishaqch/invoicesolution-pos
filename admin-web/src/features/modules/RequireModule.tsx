/**
 * Route guard. Wrap the element prop of any <Route> whose page should
 * only render when its module is enabled for the current tenant. If
 * the module is disabled, we redirect to the dashboard rather than
 * showing a 404 — the route still exists conceptually, the tenant just
 * doesn't have access. The server already returns 403 on the API side
 * (HasModule) — this is the UX layer.
 */

import { Navigate } from "react-router-dom";

import { useModules, type ModuleKey } from "./hooks";

interface Props {
  module: ModuleKey;
  children: React.ReactNode;
}

export function RequireModule({ module, children }: Props) {
  const { data, isLoading } = useModules();

  // While the modules query is loading, render nothing. We don't show a
  // spinner because most pages already have their own loading state and
  // the modules call resolves in <50ms on a warm cache.
  if (isLoading || !data) return null;

  if (!data.enabled.includes(module)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
