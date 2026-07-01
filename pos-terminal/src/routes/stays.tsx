/**
 * Stays / Rooms — the resort guest-folio hub (gated on the `hotel` module).
 *
 * Three views:
 *   list   — open stays + "Open new stay"
 *   open   — form to check a guest in (guest details, room, check-in/out)
 *   detail — a folio's running charges, "Add charges", and checkout
 *
 * A folio groups room nights (auto-charged on open) + daily restaurant charges;
 * checkout prints ONE consolidated bill and frees the room.
 */
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { rs } from "@/lib/money";
import { useSessionStore } from "@/stores/session";

import { FolioDetail } from "@/features/hotel/FolioDetail";
import { OpenStayForm } from "@/features/hotel/OpenStayForm";
import { listOpenFolios, type FolioRow } from "@/features/hotel/api";

type View = { name: "list" } | { name: "open" } | { name: "detail"; folioId: string };

export default function StaysRoute() {
  const navigate = useNavigate();
  const toast = useToast();
  const tenant = useSessionStore((s) => s.tenant);
  const [view, setView] = useState<View>({ name: "list" });
  const [folios, setFolios] = useState<FolioRow[]>([]);
  const [loading, setLoading] = useState(true);

  // Hotel module gate — bounce non-hotel tenants back to the till.
  useEffect(() => {
    if (!(tenant?.modules_enabled ?? []).includes("hotel")) navigate("/sale", { replace: true });
  }, [tenant, navigate]);

  async function refresh() {
    setLoading(true);
    try {
      setFolios(await listOpenFolios());
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (view.name === "list") void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.name]);

  if (view.name === "open") {
    return (
      <OpenStayForm
        onCancel={() => setView({ name: "list" })}
        onOpened={(folioId) => {
          toast.show({ message: "Stay opened — room charged.", variant: "success" });
          setView({ name: "detail", folioId });
        }}
      />
    );
  }

  if (view.name === "detail") {
    return (
      <FolioDetail
        folioId={view.folioId}
        onBack={() => setView({ name: "list" })}
        onCheckedOut={() => {
          toast.show({ message: "Checked out — bill printed.", variant: "success" });
          setView({ name: "list" });
        }}
      />
    );
  }

  // --- list view ---
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <button
          type="button"
          onClick={() => navigate("/sale")}
          className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
        >
          <ArrowLeft className="h-4 w-4" /> Till
        </button>
        <div className="text-sm font-semibold">Stays / Rooms</div>
        <Button size="sm" onClick={() => setView({ name: "open" })}>
          + Open new stay
        </Button>
      </header>

      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="p-6 text-center text-sm text-muted-foreground">Loading…</div>
        ) : folios.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">
            No guests checked in. Tap <b>Open new stay</b> to check a guest in.
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {folios.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setView({ name: "detail", folioId: f.id })}
                className="rounded-lg border bg-background p-4 text-left transition-colors hover:bg-muted"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{f.guest_name}</span>
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                    {f.room_number ?? "—"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{f.guest_phone}</div>
                <div className="mt-2 text-xs">
                  <span className="text-muted-foreground">Folio </span>
                  <span className="font-mono">{f.folio_number}</span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  In: {fmtDate(f.check_in)}
                  {f.expected_check_out && ` · Out: ${fmtDate(f.expected_check_out)}`}
                  {` · ${f.nights} night${f.nights === 1 ? "" : "s"}`}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    const data = e.data as Record<string, unknown> | null;
    if (data) {
      if (typeof data.detail === "string") return data.detail;
      for (const v of Object.values(data)) {
        if (Array.isArray(v) && typeof v[0] === "string") return v[0];
        if (typeof v === "string") return v;
      }
    }
    return `Request failed (HTTP ${e.status}).`;
  }
  return "Something went wrong. Check your connection and try again.";
}

// Re-export rs so feature components share the formatter without a deep import.
export { rs };
