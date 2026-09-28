/**
 * Thin fetch wrapper (ported from admin-web/src/lib/api.ts):
 *   - prefixes /api on relative paths
 *   - attaches Bearer token from the waiter auth store
 *   - on 401: refresh once -> retry; if refresh fails, lock() (returns to the
 *     PIN screen but KEEPS the device pairing — a waiter re-auths, the tablet
 *     stays paired).
 *
 * Pairing + pin-login + refresh calls pass { auth: false } so they never try to
 * attach/refresh a token.
 *
 * Vite's dev server proxies /api -> backend (vite.config.ts).
 */

import { useAuthStore } from "@/stores/auth";

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(`API ${status}`);
  }
}

/** Turn an ApiError (DRF validation shape) into an operator-readable string. */
export function extractApiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.data as Record<string, unknown> | string | null | undefined;
    if (d && typeof d === "object") {
      const obj = d as Record<string, unknown>;
      if (typeof obj.detail === "string") return obj.detail;
      const nonField = obj.non_field_errors;
      if (Array.isArray(nonField) && nonField.length) return String(nonField[0]);
      const parts: string[] = [];
      for (const [k, v] of Object.entries(obj)) {
        if (k === "detail" || k === "non_field_errors") continue;
        if (Array.isArray(v) && v.length) parts.push(`${k}: ${v[0]}`);
        else if (typeof v === "string") parts.push(`${k}: ${v}`);
      }
      if (parts.length) return parts.join("; ");
    } else if (typeof d === "string" && d) {
      return d;
    }
    return `Request failed (HTTP ${err.status}).`;
  }
  return err instanceof Error ? err.message : "Request failed.";
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean; retried?: boolean } = { auth: true },
): Promise<T> {
  const url = path.startsWith("/") ? `${BASE}${path}` : `${BASE}/${path}`;
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const access = useAuthStore.getState().access;

  // No token = waiter not signed in (or was locked out). Short-circuit so we
  // don't fire a request that just yields another 401 storm.
  if (options.auth && !access) {
    throw new ApiError(401, { detail: "Not authenticated" });
  }

  if (options.auth && access) {
    headers.set("Authorization", `Bearer ${access}`);
  }

  const resp = await fetch(url, { ...init, headers });

  if (resp.status === 401 && options.auth && !options.retried) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return api<T>(path, init, { ...options, retried: true });
    }
    // Refresh failed -> lock the waiter out (KEEP device pairing).
    useAuthStore.getState().lock();
    throw new ApiError(401, await resp.json().catch(() => null));
  }

  if (!resp.ok) {
    let body: unknown = null;
    try {
      body = await resp.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(resp.status, body);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

async function tryRefresh(): Promise<boolean> {
  const refresh = useAuthStore.getState().refresh;
  if (!refresh) return false;
  try {
    const resp = await fetch(`${BASE}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as { access: string; refresh?: string };
    useAuthStore.getState().setTokens(data.access, data.refresh ?? refresh);
    return true;
  } catch {
    return false;
  }
}
