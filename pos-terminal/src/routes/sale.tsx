import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { CartPane } from "@/features/sale/CartPane";
import { ProductGrid } from "@/features/sale/ProductGrid";
import { TotalsPane } from "@/features/sale/TotalsPane";
import { useInitialCatalogSync } from "@/features/catalog/useInitialSync";
import { usePosContext } from "@/features/sale/usePosContext";
import { SyncStatusDot } from "@/features/sync/SyncStatusDot";
import { useSaleStore } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";

export default function SaleRoute() {
  const navigate = useNavigate();
  const ctx = usePosContext();
  const sync = useInitialCatalogSync();
  const user = useSessionStore((s) => s.user);
  const tenant = useSessionStore((s) => s.tenant);
  const role = useSessionStore((s) => s.role);
  const logout = useSessionStore((s) => s.logout);

  const addLine = useSaleStore((s) => s.addLine);
  const lines = useSaleStore((s) => s.lines);
  const setStage = useSaleStore((s) => s.setStage);

  const [holdLabel, setHoldLabel] = useState<string | null>(null);

  // Gate: route to day-open if no session is open.
  if (!ctx.loading && ctx.terminal && !ctx.session) {
    navigate("/day-open", { replace: true });
    return null;
  }

  const onLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  function onHold() {
    if (lines.length === 0) return;
    const label = window.prompt("Hold sale — enter a label (e.g., customer name):");
    if (!label) return;
    // For Phase 2, holding the cart only affects the in-memory cart.
    // Phase 3 will persist held drafts to SQLite through the sync engine.
    setHoldLabel(label);
    useSaleStore.getState().resetForNewSale();
    window.alert(`Sale held as "${label}". (Recall list available from header.)`);
    setStage("empty");
  }

  if (sync.status === "syncing" && sync.productsLocal === 0) {
    return <Splash msg="Loading catalog…" />;
  }
  if (sync.status === "error") {
    return <Splash msg={`Couldn't reach the server: ${sync.error}`} variant="error" />;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between border-b px-4">
        <div className="text-xs text-muted-foreground">
          {tenant?.business_name ?? "—"} · {ctx.branch?.name ?? "—"} · {ctx.terminal?.name ?? "—"}
          {ctx.session && ctx.session.opened_with_amount && (
            <span className="ml-2">· Float Rs {ctx.session.opened_with_amount}</span>
          )}
          {holdLabel && <span className="ml-2 text-amber-700">· Held: {holdLabel}</span>}
        </div>
        <div className="flex items-center gap-3">
          <SyncStatusDot />
          <button
            type="button"
            onClick={() => navigate("/held-sales")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            Held sales
          </button>
          <button
            type="button"
            onClick={() => navigate("/return")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            Return
          </button>
          <button
            type="button"
            onClick={() => navigate("/day-close")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            Day close
          </button>
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

      <main className="grid flex-1 grid-cols-12 gap-3 overflow-hidden p-3">
        <div className="col-span-5 overflow-hidden">
          <ProductGrid onAdd={addLine} />
        </div>
        <div className="col-span-4 overflow-hidden rounded-md border bg-background">
          <CartPane />
        </div>
        <div className="col-span-3 overflow-hidden">
          <TotalsPane onHold={onHold} />
        </div>
      </main>
    </div>
  );
}

function Splash({
  msg,
  variant = "info",
}: {
  msg: string;
  variant?: "info" | "error";
}) {
  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <div
        className={`text-sm ${
          variant === "error" ? "text-destructive" : "text-muted-foreground"
        }`}
      >
        {msg}
      </div>
    </div>
  );
}
