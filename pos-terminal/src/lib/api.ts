/**
 * POS-side API client. Mirrors admin-web/lib/api shape, but reads access
 * token from the session store (zustand).
 */

import { useSessionStore } from "@/stores/session";

const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000") + "/api";

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(`API ${status}`);
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean } = { auth: true },
): Promise<T> {
  const url = path.startsWith("/") ? `${BASE}${path}` : `${BASE}/${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  const access = useSessionStore.getState().access;
  if (options.auth && access) {
    headers.set("Authorization", `Bearer ${access}`);
  }

  const resp = await fetch(url, { ...init, headers });

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
