import { useNavigate } from "react-router-dom";

import { useSessionStore } from "@/stores/session";

const BRANCH_NAME = import.meta.env.VITE_BRANCH_NAME ?? "—";
const TERMINAL_NAME = import.meta.env.VITE_TERMINAL_NAME ?? "Terminal";

export default function SaleRoute() {
  const navigate = useNavigate();
  const user = useSessionStore((s) => s.user);
  const tenant = useSessionStore((s) => s.tenant);
  const role = useSessionStore((s) => s.role);
  const logout = useSessionStore((s) => s.logout);

  const onLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between border-b px-4">
        <div className="text-xs text-muted-foreground">
          {tenant?.business_name ?? "—"} · {BRANCH_NAME} · {TERMINAL_NAME}
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right text-xs leading-tight">
            <div className="font-medium">{user?.full_name}</div>
            <div className="text-muted-foreground capitalize">{role ?? "—"}</div>
          </div>
          <button
            onClick={onLogout}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center p-8">
        <div className="text-center">
          <div className="text-2xl font-semibold tracking-tight">
            Welcome{user ? `, ${user.full_name}` : ""}.
          </div>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            The product grid, cart, and payment flow land in Phase 2. This screen
            confirms identity, tenancy, and offline-capable storage are wired
            correctly on the terminal.
          </p>
        </div>
      </main>
    </div>
  );
}
