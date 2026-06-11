import { useEffect, type ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

import { GlobalLoadingBar } from "./GlobalLoadingBar";
import { Sidebar } from "./Sidebar";
import { SyncBanner } from "./SyncBanner";
import { TopBar } from "./TopBar";

interface MeResponse {
  user: unknown;
  tenant: import("@pos/shared/types").Tenant | null;
  role: import("@pos/shared/types").Role | null;
}

/**
 * Refresh the persisted tenant blob from /auth/me on every shell mount.
 *
 * Two responsibilities:
 *
 *   1. Pick up tenant fields that may have been added since this user
 *      last signed in (e.g. logo_url, business_name updates from the
 *      platform admin). The auth store is persisted to localStorage,
 *      so without this refresh stale users would never see new fields.
 *
 *   2. **Auto-logout when /auth/me reports no tenant.** The persisted
 *      access token can be valid (so the API doesn't 401) yet point at
 *      a tenant the user no longer has an active membership in — every
 *      tenant-scoped endpoint then 403s with "You are not an active
 *      member of this tenant." The UI gets stuck in a poll loop that
 *      can't recover. Logging out forces a fresh login, which mints a
 *      new JWT with the correct tenant_id claim.
 *
 * Cheap: one GET on shell mount. Errors are swallowed (we'd rather
 * keep the stale tenant blob than crash the chrome).
 */
function useTenantRefresh() {
  const access = useAuthStore((s) => s.access);
  const setTenant = useAuthStore((s) => s.setTenant);
  const logout = useAuthStore((s) => s.logout);
  useEffect(() => {
    if (!access) return;
    let cancelled = false;
    api<MeResponse>("/auth/me/")
      .then((data) => {
        if (cancelled) return;
        if (data.tenant === null) {
          // Token valid but no active membership — every tenant
          // endpoint will 403. Bounce to /login.
          logout();
          return;
        }
        setTenant(data.tenant);
      })
      .catch(() => { /* stale tenant beats no tenant */ });
    return () => { cancelled = true; };
  }, [access, setTenant, logout]);
}

export function AdminShell({ children }: { children: ReactNode }) {
  useTenantRefresh();
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <GlobalLoadingBar />
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to main content
      </a>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <SyncBanner />
        <main id="main-content" className="flex-1 overflow-auto p-4 md:p-6" role="main">
          {children}
        </main>
      </div>
    </div>
  );
}
