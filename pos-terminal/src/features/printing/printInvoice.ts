/**
 * Print (or re-print) a customer receipt for an invoice that's already
 * persisted to local SQLite.
 *
 * Loads the full invoice + items + payments from local SQLite via the
 * sales:get IPC, then hands it to the printer adapter. Used by:
 *   - SuccessRoute  → "Print receipt" button after checkout
 *   - SuccessRoute  → auto re-print once FBR returns the invoice number
 *                     (so the printed receipt has the FBR # + QR)
 *   - TodayInvoicesRoute → "Print" button per row, for past sales
 *   - HeldSalesRoute → not currently used (held sales don't print)
 *
 * Returns the result the printer adapter returned so the caller can
 * surface a non-blocking toast on failure.
 */

import { useSessionStore } from "@/stores/session";

export type PrintResult = {
  success: boolean;
  reason?: string;
  fallbackPath?: string;
  /** True when there was no invoice to print (caller should warn). */
  notFound?: boolean;
};

export async function printInvoiceById(
  invoice_id: string,
  opts: { width?: 48 | 32 } = {},
): Promise<PrintResult> {
  const detail = await window.api.sales.get(invoice_id);
  if (!detail) return { success: false, notFound: true };

  const tenant = useSessionStore.getState().tenant;
  return window.api.printer.print({
    business_name: tenant?.business_name ?? "POS",
    branch_name: "",
    ntn: tenant?.ntn ?? "",
    invoice: detail.invoice as never,
    items: detail.items as never,
    payments: detail.payments as never,
    width: opts.width ?? 48,
  });
}
