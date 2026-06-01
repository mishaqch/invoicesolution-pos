/**
 * Device pairing (main process).
 *
 * On first launch the terminal has no identity. The owner creates a Terminal
 * in admin-web and hands the cashier a one-time pairing code. The cashier types
 * it into the terminal; we redeem it against the cloud via POST /api/terminals/
 * pair/, which binds THIS machine (device fingerprint) to that terminal slot and
 * returns the branch identity needed to ring sales + fiscalize.
 *
 * The pairing result is persisted to kv_meta so the terminal "remembers" its
 * branch + terminal across restarts and never has to pick "the first branch"
 * again. Cashier auth (email + PIN) is separate and happens after pairing.
 */

import { createHash } from "node:crypto";
import os from "node:os";

import { getMeta, setMeta } from "./db/client";

// kv_meta keys the rest of the app reads to learn its identity.
export const PAIR_KEYS = {
  terminalId: "pair.terminal_id",
  terminalName: "pair.terminal_name",
  terminalIndex: "pair.terminal_index",
  branchId: "pair.branch_id",
  branchName: "pair.branch_name",
  branchCode: "pair.branch_code",
  branchFbrPosId: "pair.branch_fbr_pos_id",
  tenantId: "pair.tenant_id",
  tenantName: "pair.tenant_name",
  sdcUrl: "pair.sdc_url",          // FBR Fiscalization service base (default localhost:8524)
  deviceFingerprint: "pair.device_fingerprint",
  pairedAt: "pair.paired_at",
} as const;

export interface PairedIdentity {
  terminalId: string;
  terminalName: string;
  terminalIndex: number;
  branchId: string;
  branchName: string;
  branchCode: string;
  branchFbrPosId: string | null;
  tenantId: string;
  tenantName: string;
  sdcUrl: string;
}

/**
 * A stable per-machine fingerprint = hostname + the first non-internal MAC,
 * hashed. The MAC is exactly what FBR binds the POS registration to, so this
 * lines up with the FBR-side identity. Stored once on first computation so it
 * never drifts for a machine that has already paired.
 */
export function deviceFingerprint(): string {
  const existing = getMeta(PAIR_KEYS.deviceFingerprint);
  if (existing) return existing;

  const nics = os.networkInterfaces();
  const mac =
    Object.values(nics)
      .flat()
      .find((n) => n && !n.internal && n.mac && n.mac !== "00:00:00:00:00:00")?.mac ?? "";
  const raw = `${os.hostname()}|${mac}`;
  const hash = createHash("sha256").update(raw).digest("hex").slice(0, 32);
  const fp = `win-${hash}`;
  setMeta(PAIR_KEYS.deviceFingerprint, fp);
  return fp;
}

export function isPaired(): boolean {
  return !!getMeta(PAIR_KEYS.terminalId) && !!getMeta(PAIR_KEYS.branchId);
}

export function getPairedIdentity(): PairedIdentity | null {
  if (!isPaired()) return null;
  return {
    terminalId: getMeta(PAIR_KEYS.terminalId)!,
    terminalName: getMeta(PAIR_KEYS.terminalName) ?? "",
    terminalIndex: Number(getMeta(PAIR_KEYS.terminalIndex) ?? "1"),
    branchId: getMeta(PAIR_KEYS.branchId)!,
    branchName: getMeta(PAIR_KEYS.branchName) ?? "",
    branchCode: getMeta(PAIR_KEYS.branchCode) ?? "",
    branchFbrPosId: getMeta(PAIR_KEYS.branchFbrPosId) || null,
    tenantId: getMeta(PAIR_KEYS.tenantId) ?? "",
    tenantName: getMeta(PAIR_KEYS.tenantName) ?? "",
    sdcUrl: getMeta(PAIR_KEYS.sdcUrl) || "http://localhost:8524",
  };
}

/** Resolve the SDC base URL — the paired value, overridable via Hardware. */
export function getSdcUrl(): string {
  return getMeta(PAIR_KEYS.sdcUrl) || "http://localhost:8524";
}

export function setSdcUrl(url: string): void {
  setMeta(PAIR_KEYS.sdcUrl, url.trim());
}

interface PairResponse {
  tenant_id: string;
  tenant_name: string;
  branch_id: string;
  branch_name: string;
  branch_code: string;
  branch_fbr_pos_id: string | null;
  terminal_id: string;
  terminal_name: string;
  terminal_index: number;
  sdc_url: string;
}

/**
 * Redeem a pairing code against the cloud and persist the resulting identity.
 * Returns the paired identity on success; throws with a human message on
 * failure (bad/expired code, network, already-bound machine).
 */
export async function pairWithCode(
  apiBase: string,
  pairingCode: string,
  appVersion: string,
): Promise<PairedIdentity> {
  const fingerprint = deviceFingerprint();
  const url = `${apiBase.replace(/\/$/, "")}/api/terminals/pair/`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pairing_code: pairingCode.trim().toUpperCase(),
        device_fingerprint: fingerprint,
        os_version: `${os.type()} ${os.release()}`,
        app_version: appVersion,
      }),
    });
  } catch {
    throw new Error("Could not reach the server. Check the internet connection and try again.");
  }

  if (!resp.ok) {
    let detail = `Pairing failed (${resp.status}).`;
    try {
      const body = (await resp.json()) as Record<string, unknown>;
      const firstErr =
        (body.pairing_code as string[])?.[0] ??
        (body.device_fingerprint as string[])?.[0] ??
        (body.detail as string);
      if (firstErr) detail = String(firstErr);
    } catch {
      /* keep generic */
    }
    throw new Error(detail);
  }

  const data = (await resp.json()) as PairResponse;
  setMeta(PAIR_KEYS.terminalId, data.terminal_id);
  setMeta(PAIR_KEYS.terminalName, data.terminal_name);
  setMeta(PAIR_KEYS.terminalIndex, String(data.terminal_index));
  setMeta(PAIR_KEYS.branchId, data.branch_id);
  setMeta(PAIR_KEYS.branchName, data.branch_name);
  setMeta(PAIR_KEYS.branchCode, data.branch_code);
  setMeta(PAIR_KEYS.branchFbrPosId, data.branch_fbr_pos_id ?? "");
  setMeta(PAIR_KEYS.tenantId, data.tenant_id);
  setMeta(PAIR_KEYS.tenantName, data.tenant_name);
  setMeta(PAIR_KEYS.sdcUrl, data.sdc_url || "http://localhost:8524");
  setMeta(PAIR_KEYS.pairedAt, new Date().toISOString());

  return getPairedIdentity()!;
}

/** Forget the paired identity (Hardware → "Unpair this terminal"). */
export function unpair(): void {
  for (const k of Object.values(PAIR_KEYS)) {
    if (k === PAIR_KEYS.deviceFingerprint) continue; // keep the machine id stable
    setMeta(k, "");
  }
}
