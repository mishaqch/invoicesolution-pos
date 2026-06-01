/**
 * Active terminal-driven FBR fiscalization (the SDC path).
 *
 * Unlike useFbrConfirmation (which passively polls and waits for the CLOUD to
 * fiscalize), this hook makes the TERMINAL the driver: as soon as the invoice
 * exists on the server, it calls the local FBR SDC (localhost:8524) via the
 * main process, persists the fiscal number, and reprints the receipt WITH the
 * QR. This is the "submit to FBR → verified → print" flow.
 *
 * Speed + offline safety:
 *   - The sale already printed a provisional receipt immediately (offline-first
 *     never blocks the counter). This hook upgrades it to a fiscalized receipt.
 *   - We poll briefly for the invoice to land on the server (the sync worker
 *     pushes it within ~1s on a healthy network), then fiscalize once.
 *   - If the invoice never reaches the server (offline) or the SDC is down, we
 *     simply stop — the sync worker + cloud reconcile later and the success
 *     screen's slower fallback poll still reprints when the number arrives.
 */

import { useEffect, useRef } from "react";

import { ApiError, api } from "@/lib/api";

interface InvoiceStatusResponse {
  id: string;
  status: string;
  fbr_invoice_number: string | null;
  fbr_qr_payload: string | null;
  branch_fbr_pos_id?: string | null;
}

interface Options {
  invoiceId: string | undefined;
  /** Called with the FBR number once fiscalized (to reprint + update UI). */
  onFiscalized?: (fbrInvoiceNumber: string) => void;
  /** Called when fiscalization can't complete now (offline/SDC down). */
  onDeferred?: (reason: string) => void;
}

// Poll fast for the invoice to exist on the server, then fiscalize. The sync
// worker normally pushes within a second on a healthy network.
const EXIST_POLL_MS = 700;
const EXIST_MAX_ATTEMPTS = 8; // ~5.6s ceiling waiting for the invoice to sync

export function useTerminalFiscalize({ invoiceId, onFiscalized, onDeferred }: Options) {
  const startedRef = useRef(false);

  useEffect(() => {
    if (!invoiceId || startedRef.current) return;
    startedRef.current = true;
    let cancelled = false;
    let attempts = 0;

    const run = async () => {
      // 1. Wait (briefly) for the invoice to reach the server.
      while (!cancelled && attempts < EXIST_MAX_ATTEMPTS) {
        attempts += 1;
        try {
          const inv = await api<InvoiceStatusResponse>(`/sales/invoices/${invoiceId}/`);
          // Already fiscalized (cloud beat us to it) — nothing to do.
          if (inv.fbr_invoice_number) {
            onFiscalized?.(inv.fbr_invoice_number);
            return;
          }
          // Not an SDC branch → leave to the DI-API/cloud path.
          if (inv.branch_fbr_pos_id === null || inv.branch_fbr_pos_id === undefined) {
            onDeferred?.("not an SDC branch");
            return;
          }
          // Invoice exists + needs fiscalizing → do it via the local SDC.
          const res = await window.api.fiscalize.invoice(invoiceId);
          if (res.ok && res.fbrInvoiceNumber) {
            onFiscalized?.(res.fbrInvoiceNumber);
          } else {
            onDeferred?.(res.reason ?? "fiscalization deferred");
          }
          return;
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            // Not synced yet — wait and retry.
            await new Promise((r) => setTimeout(r, EXIST_POLL_MS));
            continue;
          }
          onDeferred?.("could not reach server");
          return;
        }
      }
      if (!cancelled) onDeferred?.("invoice not yet synced");
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [invoiceId, onFiscalized, onDeferred]);
}
