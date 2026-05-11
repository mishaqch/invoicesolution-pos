import { Building2, LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

/**
 * Top bar shown above every page inside the AdminShell.
 *
 * Left:  tenant chip with the business icon + name
 * Right: user info (name + role badge) + sign-out icon button
 *
 * Uses the brand palette so the chrome reads consistently with the
 * rest of the redesigned theme.
 */
export function TopBar() {
  const tenant = useAuthStore((s) => s.tenant);
  const user = useAuthStore((s) => s.user);
  const role = useAuthStore((s) => s.role);
  const refresh = useAuthStore((s) => s.refresh);
  const logout = useAuthStore((s) => s.logout);

  const onLogout = async () => {
    if (refresh) {
      try {
        await api("/auth/logout/", {
          method: "POST",
          body: JSON.stringify({ refresh }),
        });
      } catch { /* swallow */ }
    }
    logout();
  };

  // Compact first-initial avatar for the user. Keeps the bar tight at
  // narrow viewports where a long name would push the logout button
  // off the screen.
  const initial = (user?.full_name ?? user?.email ?? "?").charAt(0).toUpperCase();

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur-sm">
      <div className="flex items-center gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary-soft text-primary-soft-foreground">
          <Building2 className="h-3.5 w-3.5" aria-hidden />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">
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
        <div className="hidden text-right text-xs leading-tight md:block">
          <div className="font-medium">{user?.full_name ?? user?.email}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {role ?? "—"}
          </div>
        </div>
        <div className="flex h-9 w-9 select-none items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary-soft-foreground">
          {initial}
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onLogout}
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
