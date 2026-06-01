/**
 * Direct FBR fiscalization from the terminal (main process).
 *
 * The terminal runs ON the Windows machine that hosts the FBR Fiscalization
 * service (SDC) at localhost:8524 — so unlike the cloud, it can reach the SDC
 * directly. The three-step dance:
 *
 *   1. GET  /api/sales/invoices/{id}/fiscal-payload/  (cloud, authed)
 *        → the exact SDC request body + the SDC submit path, built server-side
 *          from the canonical builder so the wire format has one owner.
 *   2. POST {sdcUrl}{sdc_submit_path}                 (local SDC, no auth)
 *        → FBR fiscal invoice number.
 *   3. POST /api/sales/invoices/{id}/fiscal-result/   (cloud, authed, idempotent)
 *        → persist the FBR number + QR; invoice flips to status=valid.
 *
 * Speed matters at the counter: we cap the SDC call at a tight timeout. On
 * success the receipt prints WITH the FBR QR. On timeout/offline the caller
 * falls back to printing immediately and retrying fiscalization in the
 * background (the SDC step is idempotent server-side via fiscal-result).
 *
 * This is done in the main process (not the renderer) so the call to the local
 * SDC isn't subject to the renderer's web-origin/mixed-content restrictions,
 * and so it can run headless in the background.
 */

import { getMeta } from "./db/client";
import { getSdcUrl } from "./pairing";

// Tight cap so a slow/unreachable SDC never holds the customer at the counter.
const SDC_TIMEOUT_MS = 3500;
const CLOUD_TIMEOUT_MS = 8000;

export interface FiscalizeResult {
  ok: boolean;
  fbrInvoiceNumber?: string;
  alreadyFiscalized?: boolean;
  reason?: string;
}

function accessToken(): string | null {
  return getMeta("access_token");
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  ms: number,
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fiscalize one invoice via the local SDC. `apiBase` is the cloud backend.
 * Returns a structured result; never throws (callers branch on `ok`).
 */
export async function fiscalizeInvoice(
  apiBase: string,
  invoiceId: string,
): Promise<FiscalizeResult> {
  const token = accessToken();
  if (!token) return { ok: false, reason: "not signed in" };
  const base = apiBase.replace(/\/$/, "");
  const authHeaders = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  // 1. Ask the cloud for the SDC request body.
  let payloadResp: Response;
  try {
    payloadResp = await fetchWithTimeout(
      `${base}/api/sales/invoices/${invoiceId}/fiscal-payload/`,
      { method: "GET", headers: authHeaders },
      CLOUD_TIMEOUT_MS,
    );
  } catch {
    return { ok: false, reason: "cloud unreachable (fiscal-payload)" };
  }
  if (!payloadResp.ok) {
    return { ok: false, reason: `fiscal-payload ${payloadResp.status}` };
  }
  const payload = (await payloadResp.json()) as {
    already_fiscalized?: boolean;
    fbr_invoice_number?: string | null;
    branch_fbr_pos_id?: string | null;
    sdc_submit_path?: string;
    sdc_payload?: Record<string, unknown> | null;
  };

  if (payload.already_fiscalized && payload.fbr_invoice_number) {
    return { ok: true, alreadyFiscalized: true, fbrInvoiceNumber: payload.fbr_invoice_number };
  }
  if (!payload.branch_fbr_pos_id) {
    return { ok: false, reason: "branch has no FBR POS ID (not an SDC branch)" };
  }
  if (!payload.sdc_payload || !payload.sdc_submit_path) {
    return { ok: false, reason: "no SDC payload returned" };
  }

  // 2. Submit to the local SDC.
  const sdcUrl = getSdcUrl().replace(/\/$/, "");
  let sdcResp: Response;
  try {
    sdcResp = await fetchWithTimeout(
      `${sdcUrl}${payload.sdc_submit_path}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload.sdc_payload),
      },
      SDC_TIMEOUT_MS,
    );
  } catch {
    return { ok: false, reason: "SDC unreachable/slow — will retry in background" };
  }
  if (!sdcResp.ok) {
    return { ok: false, reason: `SDC HTTP ${sdcResp.status}` };
  }

  // The SDC echoes FBR's response. Success is Code "100"; the fiscal number
  // is in InvoiceNumber. Field names mirror apps/fbr/sdc_client.parse_sdc_response.
  let sdcBody: Record<string, unknown>;
  try {
    sdcBody = (await sdcResp.json()) as Record<string, unknown>;
  } catch {
    return { ok: false, reason: "SDC returned non-JSON" };
  }
  const code = String(sdcBody.Code ?? sdcBody.code ?? "");
  const fbrNumber = String(
    sdcBody.InvoiceNumber ?? sdcBody.invoiceNumber ?? sdcBody.FBRInvoiceNumber ?? "",
  ).trim();
  if (code !== "100" || !fbrNumber) {
    const msg =
      (sdcBody.Response as string) ||
      (sdcBody.Errors as string) ||
      `SDC rejected (Code=${code})`;
    return { ok: false, reason: String(msg) };
  }

  // 3. Persist the FBR number to the cloud (idempotent, immutable once set).
  try {
    const resultResp = await fetchWithTimeout(
      `${base}/api/sales/invoices/${invoiceId}/fiscal-result/`,
      {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ fbr_invoice_number: fbrNumber }),
      },
      CLOUD_TIMEOUT_MS,
    );
    if (!resultResp.ok && resultResp.status !== 409) {
      // We HAVE the FBR number from the SDC; the cloud persist failed. The
      // background sync poll will reconcile, so still report success with the
      // number we obtained.
      return { ok: true, fbrInvoiceNumber: fbrNumber, reason: "cloud persist deferred" };
    }
  } catch {
    return { ok: true, fbrInvoiceNumber: fbrNumber, reason: "cloud persist deferred" };
  }

  return { ok: true, fbrInvoiceNumber: fbrNumber };
}

/**
 * Probe the local SDC's health endpoint. Used by the Hardware screen's
 * "Test SDC connection" button. Returns a short status string.
 */
export async function checkSdcHealth(): Promise<{ ok: boolean; message: string }> {
  const sdcUrl = getSdcUrl().replace(/\/$/, "");
  try {
    const resp = await fetchWithTimeout(
      `${sdcUrl}/api/IMSFiscal/get`,
      { method: "GET" },
      SDC_TIMEOUT_MS,
    );
    if (resp.ok) {
      const text = await resp.text();
      return { ok: true, message: text.slice(0, 200) || "SDC is responding." };
    }
    return { ok: false, message: `SDC returned HTTP ${resp.status}` };
  } catch {
    return { ok: false, message: `Could not reach SDC at ${sdcUrl}` };
  }
}
