import { Building2, Menu } from "lucide-react";
import { useState } from "react";

import { useAuthStore } from "@/stores/auth";
import { useSidebarStore } from "@/stores/sidebar";

import { ProfileMenu } from "./ProfileMenu";

/**
 * Top bar shown above every page inside the AdminShell.
 *
 * Left:  hamburger (mobile) + tenant chip with the business icon + name
 * Right: profile menu — avatar dropdown with user info + Settings + Sign out.
 *
 * Uses the brand palette so the chrome reads consistently with the
 * rest of the redesigned theme.
 */
export function TopBar() {
  const tenant = useAuthStore((s) => s.tenant);

  // Tenant logo with broken-image fallback. If the upload URL 404s or
  // the host blocks hotlinking we drop back to the Building2 glyph
  // instead of rendering the browser's broken-image icon.
  const [logoBroken, setLogoBroken] = useState(false);
  const hasLogo = Boolean(tenant?.logo_url) && !logoBroken;

  const toggleSidebar = useSidebarStore((s) => s.toggle);

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur-sm">
      <div className="flex min-w-0 items-center gap-2.5">
        {/* Hamburger — opens the nav drawer on mobile; hidden on desktop where
            the sidebar is always visible. */}
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label="Open navigation"
          className="-ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-foreground/70 hover:bg-accent md:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md bg-primary-soft text-primary-soft-foreground">
          {hasLogo ? (
            <img
              src={tenant!.logo_url!}
              alt=""
              className="h-full w-full object-cover"
              onError={() => setLogoBroken(true)}
            />
          ) : (
            <Building2 className="h-3.5 w-3.5" aria-hidden />
          )}
        </div>
        <div className="flex min-w-0 flex-col leading-tight">
          <span
            className="truncate text-sm font-semibold"
            title={tenant?.business_name ?? undefined}
          >
            {tenant?.business_name ?? "No tenant"}
          </span>
          {tenant?.ntn && (
            <span className="text-[10px] text-muted-foreground tabular-nums">
              NTN {tenant.ntn}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <ProfileMenu />
      </div>
    </header>
  );
}
