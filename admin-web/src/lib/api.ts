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

export async function api<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean; retried?: boolean } = { auth: true },
): Promise<T> {
  const url = path.startsWith("/") ? `${BASE}${path}` : `${BASE}/${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  const access = useAuthStore.getState().access;
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
