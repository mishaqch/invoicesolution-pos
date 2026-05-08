import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useInitialCatalogSync } from "@/features/catalog/useInitialSync";
import { useProductSearch } from "@/features/catalog/useProducts";
import { useSessionStore } from "@/stores/session";

const BRANCH_NAME = import.meta.env.VITE_BRANCH_NAME ?? "—";
const TERMINAL_NAME = import.meta.env.VITE_TERMINAL_NAME ?? "Terminal";

export default function SaleRoute() {
  const navigate = useNavigate();
  const user = useSessionStore((s) => s.user);
  const tenant = useSessionStore((s) => s.tenant);
  const role = useSessionStore((s) => s.role);
  const logout = useSessionStore((s) => s.logout);

  const sync = useInitialCatalogSync();
  const [query, setQuery] = useState("");
  const { results, loading } = useProductSearch(query);

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

      {sync.status === "syncing" && sync.productsLocal === 0 ? (
        <main className="flex flex-1 items-center justify-center p-8">
          <div className="text-center">
            <div className="text-lg font-medium">Loading catalog…</div>
            <div className="mt-1 text-xs text-muted-foreground">
              First sync from the server. This takes a couple of seconds.
            </div>
          </div>
        </main>
      ) : sync.status === "error" ? (
        <main className="flex flex-1 items-center justify-center p-8">
          <div className="text-center">
            <div className="text-lg font-medium text-destructive">
              Couldn't reach the server
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {sync.error}. Check your connection.
            </div>
          </div>
        </main>
      ) : (
        <main className="flex flex-1 flex-col gap-3 p-4">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Scan barcode or search products…"
            className="h-12 w-full rounded-md border bg-background px-4 text-base outline-none focus:ring-2 focus:ring-ring"
            autoFocus
          />
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="p-6 text-sm text-muted-foreground">Searching…</div>
            ) : results.length === 0 ? (
              <div className="p-6 text-sm text-muted-foreground">
                {query ? "No matches." : "Catalog is empty. Add products from the admin web."}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
                {results.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className="rounded-md border bg-background p-3 text-left transition-transform active:scale-95 hover:bg-muted"
                    onClick={() => {
                      // Cart wiring lands in Phase 2.
                      console.log("would add to cart:", p.sku);
                    }}
                  >
                    <div className="line-clamp-2 text-sm font-medium">{p.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{p.sku}</div>
                    <div className="mt-2 font-mono text-sm">Rs. {p.sale_price}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </main>
      )}
    </div>
  );
}
