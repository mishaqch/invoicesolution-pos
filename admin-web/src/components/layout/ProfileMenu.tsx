import { LogOut, Settings, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

/**
 * Header profile menu — the avatar button opens a dropdown with the signed-in
 * user's details (name, email, role, tenant) and the account actions (Settings,
 * Sign out). Replaces the bare avatar + loose logout icon. Closes on outside
 * click, Escape, or navigation.
 */
export function ProfileMenu() {
  const tenant = useAuthStore((s) => s.tenant);
  const user = useAuthStore((s) => s.user);
  const role = useAuthStore((s) => s.role);
  const refresh = useAuthStore((s) => s.refresh);
  const logout = useAuthStore((s) => s.logout);

  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const name = user?.full_name || user?.email || "Account";
  const initial = (user?.full_name ?? user?.email ?? "?").charAt(0).toUpperCase();

  // Close on outside click + Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const onLogout = async () => {
    setOpen(false);
    // Confirm — logout ends the session and is easy to tap by accident.
    if (!window.confirm("Sign out of your account?")) return;
    if (refresh) {
      try {
        await api("/auth/logout/", { method: "POST", body: JSON.stringify({ refresh }) });
      } catch { /* swallow */ }
    }
    logout();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className={cn(
          "flex h-9 w-9 select-none items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary-soft-foreground outline-none transition-shadow",
          "hover:ring-2 hover:ring-ring/40 focus-visible:ring-2 focus-visible:ring-ring",
          open && "ring-2 ring-ring",
        )}
      >
        {initial}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-[60] mt-2 w-64 overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg"
        >
          {/* Identity block */}
          <div className="flex items-start gap-3 border-b px-4 py-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary-soft-foreground">
              {initial}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold" title={name}>{name}</div>
              {user?.email && (
                <div className="truncate text-xs text-muted-foreground" title={user.email}>
                  {user.email}
                </div>
              )}
              {role && (
                <span className="mt-1 inline-block rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {role}
                </span>
              )}
            </div>
          </div>

          {/* Tenant block */}
          {tenant?.business_name && (
            <div className="border-b px-4 py-2.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Business</div>
              <div className="truncate text-sm font-medium" title={tenant.business_name}>
                {tenant.business_name}
              </div>
              {tenant.ntn && (
                <div className="text-xs text-muted-foreground tabular-nums">NTN {tenant.ntn}</div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="p-1">
            <Link
              to="/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <Settings className="h-4 w-4 text-muted-foreground" />
              Settings
            </Link>
            <Link
              to="/settings/business-profile"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <UserRound className="h-4 w-4 text-muted-foreground" />
              Business profile
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={onLogout}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-destructive hover:bg-destructive/10"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
