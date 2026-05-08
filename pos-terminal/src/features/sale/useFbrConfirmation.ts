/**
 * Polls /api/sales/invoices/<id>/ for FBR confirmation after a sale.
 *
 * When the server returns status='valid' (FBR validated), and the tenant
 * has receipt_show_qr enabled, we trigger a receipt re-print with the
 * QR payload included.
 *
 * Phase 4: this is best-effort. The Success route auto-advances after 8s
 * regardless. Confirmation that arrives later is logged but doesn't
 * change the cashier flow.
 */

import { useEffect, useRef } from "react";

import { ApiError, api } from "@/lib/api";

interface InvoiceStatusResponse {
  id: string;
  status: string;
  fbr_invoice_number: string | null;
  fbr_qr_payload: string | null;
  local_invoice_number: string;
  grand_total: string;
  paid_total: string;
  change_given: string;
  invoice_date: string;
}

interface Options {
  invoiceId: string | undefined;
  onValid?: (result: InvoiceStatusResponse) => void;
  /** Stop polling after N attempts. Default 12 → ~6 minutes at 30s. */
  maxAttempts?: number;
  /** Polling interval in ms. Default 30s. */
  intervalMs?: number;
}

export function useFbrConfirmation({
  invoiceId,
  onValid,
  maxAttempts = 12,
  intervalMs = 30_000,
}: Options) {
  const attemptsRef = useRef(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!invoiceId) return;
    attemptsRef.current = 0;

    const tick = async () => {
      attemptsRef.current += 1;
      try {
        const inv = await api<InvoiceStatusResponse>(`/sales/invoices/${invoiceId}/`);
        if (inv.status === "valid" && inv.fbr_invoice_number) {
          onValid?.(inv);
          return; // stop polling
        }
        if (inv.status === "failed" || inv.status === "cancelled") {
          return; // stop polling
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          // Invoice hasn't reached the server yet (offline mode); keep trying.
        }
      }
      if (attemptsRef.current >= maxAttempts) return;
      timerRef.current = window.setTimeout(tick, intervalMs);
    };

    timerRef.current = window.setTimeout(tick, intervalMs);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [invoiceId, maxAttempts, intervalMs, onValid]);
}
