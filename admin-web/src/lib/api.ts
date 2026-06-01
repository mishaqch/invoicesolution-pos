/**
 * Thin fetch wrapper:
 *   - prefixes /api on relative paths
 *   - attaches Bearer token from the auth store
 *   - on 401, attempts refresh once; if that fails too, signs out
 *
 * Vite's dev server proxies /api → backend (vite.config.ts), so origin
 * concerns are handled there.
 */

import { useAuthStore } from "@/stores/auth";

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(`API ${status}`);
  }
}

/**
 * Turn an `ApiError` (or any thrown value) into an operator-readable
 * message. DRF serializers return validation errors as
 * `{ field: ["message", ...], non_field_errors: ["..."], detail: "..." }`,
 * and our catch blocks otherwise display the generic "API 400" — useless.
 *
 * Strategy:
 *   - non_field_errors / detail keys win (they describe the whole error).
 *   - Otherwise join field-level errors as "field: message" so the
 *     operator can see which input is wrong.
 *   - For non-Api throwables, fall back to .message or a generic string.
 */
export function extractApiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.data as Record<string, unknown> | string | null | undefined;
    if (d && typeof d === "object") {
      const obj = d as Record<string, unknown>;
      if (typeof obj.detail === "string") return obj.detail;
      const nonField = obj.non_field_errors;
      if (Array.isArray(nonField) && nonField.length) return String(nonField[0]);
      // Field-level errors → "field: message"
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
  return err instanceof Error ? err.message : "Save failed.";
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean; retried?: boolean } = { auth: true },
): Promise<T> {
  const url = path.startsWith("/") ? `${BASE}${path}` : `${BASE}/${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  const access = useAuthStore.getState().access;

  // No token in the store = the user logged out (or was logged out by
  // a prior 401 + failed refresh). Short-circuit the fetch entirely:
  // sending the request would just yield another 401, which would
  // tryRefresh again, fail again, fire logout() (no-op now), and
  // throw — repeating every poll tick. Causes the "dozens of 401s
  // per second" storm visible in the console after session expiry.
  //
  // Throwing here lets React Query surface the error to its retry
  // logic, which defaults to `retry: 3` with exponential back-off,
  // and the polling intervals stop on auth=false hooks via the
  // standard `enabled` gates we use elsewhere.
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
    useAuthStore.getState().logout();
    throw new ApiError(401, await resp.json().catch(() => null));
  }

  if (!resp.ok) {
    let body: unknown = null;
    try {
      body = await resp.json();
    } catch { /* not JSON */ }
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
