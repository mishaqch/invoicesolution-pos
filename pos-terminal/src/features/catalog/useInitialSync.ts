import { useCallback, useEffect, useRef, useState } from "react";

import { useSessionStore } from "@/stores/session";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const POLL_MS = 5 * 60 * 1000; // periodic background re-sync interval

interface SyncState {
  status: "idle" | "syncing" | "ready" | "error";
  error: string | null;
  productsLocal: number;
  lastSyncedAt: number | null; // epoch ms of last successful sync
  /** Manually pull the latest catalog now (the "Sync" button). */
  resync: () => Promise<void>;
}

/**
 * Catalog sync for the sale screen.
 *
 *   - Runs once on login (block-until-ready so the first sale screen has
 *     products), then every POLL_MS in the background.
 *   - Exposes `resync()` so the cashier can pull NEW products on demand via a
 *     "Sync" button — no need to wait up to 5 min or re-login after the owner
 *     adds items in admin-web. Incremental (the worker sends ?since=last), so a
 *     manual sync is cheap.
 */
export function useInitialCatalogSync(): SyncState {
  const access = useSessionStore((s) => s.access);
  const [state, setState] = useState<Omit<SyncState, "resync">>({
    status: "idle", error: null, productsLocal: 0, lastSyncedAt: null,
  });
  const accessRef = useRef(access);
  accessRef.current = access;
  const inFlight = useRef(false);

  const run = useCallback(async () => {
    const token = accessRef.current;
    if (!token || inFlight.current) return;
    inFlight.current = true;
    setState((s) => ({ ...s, status: "syncing", error: null }));
    try {
      const before = await window.api.catalog.count();
      await window.api.catalog.sync({ apiBase: API_BASE, accessToken: token });
      const after = await window.api.catalog.count();
      setState({
        status: "ready",
        error: null,
        productsLocal: Math.max(before, after),
        lastSyncedAt: Date.now(),
      });
    } catch (err) {
      const localCount = await window.api.catalog.count().catch(() => 0);
      setState((s) => ({
        status: localCount > 0 ? "ready" : "error",
        error: err instanceof Error ? err.message : "sync failed",
        productsLocal: localCount,
        lastSyncedAt: s.lastSyncedAt,
      }));
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (!access) return;
    void run();
    const handle = window.setInterval(() => void run(), POLL_MS);
    return () => window.clearInterval(handle);
  }, [access, run]);

  return { ...state, resync: run };
}
