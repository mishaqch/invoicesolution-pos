import { api } from "@/lib/api";
import type { PairResponse, RosterResponse } from "@/types";

/** POST /api/terminals/pair/ (no auth) — one-time device pairing. */
export function pairTerminal(input: {
  pairing_code: string;
  device_fingerprint: string;
  os_version?: string;
  app_version?: string;
}): Promise<PairResponse> {
  return api<PairResponse>(
    "/terminals/pair/",
    { method: "POST", body: JSON.stringify(input) },
    { auth: false },
  );
}

/** POST /api/terminals/roster/ (no auth) — staff name tiles for the terminal. */
export function fetchRoster(input: {
  terminal_id: string;
  device_fingerprint: string;
}): Promise<RosterResponse> {
  return api<RosterResponse>(
    "/terminals/roster/",
    { method: "POST", body: JSON.stringify(input) },
    { auth: false },
  );
}
