import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export function TopBar() {
  const tenant = useAuthStore((s) => s.tenant);
  const user = useAuthStore((s) => s.user);
  const role = useAuthStore((s) => s.role);
  const refresh = useAuthStore((s) => s.refresh);
  const logout = useAuthStore((s) => s.logout);

  const onLogout = async () => {
    if (refresh) {
      // Best-effort blacklist; ignore errors so the local logout always wins.
      try {
        await api("/auth/logout/", {
          method: "POST",
          body: JSON.stringify({ refresh }),
        });
      } catch { /* swallow */ }
    }
    logout();
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4">
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold">
          {tenant?.business_name ?? "No tenant"}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right text-xs leading-tight">
          <div className="font-medium">{user?.full_name}</div>
          <div className="text-muted-foreground capitalize">{role ?? "—"}</div>
        </div>
        <Button variant="ghost" size="icon" onClick={onLogout} aria-label="Sign out">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
