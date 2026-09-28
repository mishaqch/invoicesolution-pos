import { api } from "@/lib/api";
import type { PinLoginResponse } from "@/types";

/** POST /api/auth/pin-login/ (no auth) — pin is EXACTLY 6 digits. */
export function pinLogin(input: { email: string; pin: string }): Promise<PinLoginResponse> {
  return api<PinLoginResponse>(
    "/auth/pin-login/",
    { method: "POST", body: JSON.stringify(input) },
    { auth: false },
  );
}

/** POST /api/auth/refresh/ (no auth). Normally the fetch wrapper refreshes for
 *  us; this is exposed for completeness. */
export function refreshToken(refresh: string): Promise<{ access: string; refresh?: string }> {
  return api<{ access: string; refresh?: string }>(
    "/auth/refresh/",
    { method: "POST", body: JSON.stringify({ refresh }) },
    { auth: false },
  );
}
