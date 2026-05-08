import { useEffect, useState } from "react";

import { useSessionStore } from "@/stores/session";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const POLL_MS = 5 * 60 * 1000; // periodic re-sync interval

interface SyncState {
  status: "idle" | "syncing" | "ready" | "error";
  error: string | null;
  productsLocal: number;
}

/**
 * Block-until-ready initial catalog sync per the Phase 1 plan. Returns a
 * status the route can use to gate the sale screen.
 */
export function useInitialCatalogSync(): SyncState {
  const access = useSessionStore((s) => s.access);
  const [state, setState] = useState<SyncState>({
    status: "idle", error: null, productsLocal: 0,
  });

  useEffect(() => {
    if (!access) return;
    let cancelled = false;

    async function go() {
      setState((s) => ({ ...s, status: "syncing", error: null }));
      try {
        const localCount = await window.api.catalog.count();
        await window.api.catalog.sync({ apiBase: API_BASE, accessToken: access ?? "" });
        const after = await window.api.catalog.count();
        if (!cancelled) {
          setState({
            status: "ready",
            error: null,
            productsLocal: Math.max(localCount, after),
          });
        }
      } catch (err) {
        if (!cancelled) {
          // First sync failed: if we have a local cache, still go through.
          const localCount = await window.api.catalog.count().catch(() => 0);
          setState({
            status: localCount > 0 ? "ready" : "error",
            error: err instanceof Error ? err.message : "sync failed",
            productsLocal: localCount,
          });
        }
      }
    }

    void go();
    const handle = window.setInterval(go, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [access]);

  return state;
}
