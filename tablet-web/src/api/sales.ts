import { api } from "@/lib/api";
import type { InvoiceListResponse } from "@/types";

/**
 * GET /api/sales/invoices/?branch=<id>&held=false&from=<todayISO>&to=<todayISO>
 * Today's COMPLETED (charged) orders for the Orders page's 2nd tab.
 *
 * IMPORTANT: filter by BRANCH ONLY, never terminal — charging happens on the
 * cashier till (a different terminal), so a terminal filter yields an
 * always-empty list.
 */
export function getTodayCompletedOrders(branchId: string): Promise<InvoiceListResponse> {
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  const d = String(today.getDate()).padStart(2, "0");
  const iso = `${y}-${m}-${d}`;
  const params = new URLSearchParams({
    branch: branchId,
    held: "false",
    from: iso,
    to: iso,
  });
  return api<InvoiceListResponse>(`/sales/invoices/?${params.toString()}`);
}
