import { uuid } from "@/lib/uuid";

/**
 * A stable per-device fingerprint. Generated once (crypto UUID) and stored in
 * localStorage under a stable key so it survives reloads and re-pairings — the
 * backend uses it to key the paired terminal + the roster call.
 */
const KEY = "tablet-device-fingerprint";

export function getDeviceFingerprint(): string {
  try {
    const existing = localStorage.getItem(KEY);
    if (existing) return existing;
    const fp = uuid();
    localStorage.setItem(KEY, fp);
    return fp;
  } catch {
    // Private-mode / storage-blocked: fall back to an ephemeral id. Pairing
    // still works for the session; it just won't persist the fingerprint.
    return uuid();
  }
}
