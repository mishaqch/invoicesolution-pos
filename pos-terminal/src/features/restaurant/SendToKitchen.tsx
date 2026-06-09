/**
 * "Send to kitchen" — fires the order to the kitchen:
 *   1. Creates/updates the SERVER open order (held invoice) so the admin
 *      Floor + KDS see it live during service (not just after payment).
 *   2. Prints a KOT for the not-yet-fired lines.
 *   3. Marks those lines fired locally (re-fire only prints new items).
 *
 * Restaurant tenants only. The server call is best-effort: if offline, we still
 * print the KOT and mark fired (the order syncs to the server at Charge), so
 * the kitchen never waits on the network.
 */

import { ChefHat } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore } from "@/stores/sale";
import { fireOpenOrder } from "./api";

export function SendToKitchen({
  branchId,
  terminalId,
}: {
  branchId: string | null;
  terminalId: string | null;
}) {
  const lines = useSaleStore((s) => s.lines);
  const updateLine = useSaleStore((s) => s.updateLine);
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const unsent = lines.filter((l) => !l.sent_to_kitchen);

  async function fire() {
    if (unsent.length === 0) {
      toast.show({ message: "Nothing new to send — all items already in the kitchen.", variant: "warning" });
      return;
    }
    setBusy(true);
    const st = useSaleStore.getState();
    const orderNumber = st.clientUuid.slice(0, 8);

    // 1) Create/update the server open order (live KDS/Floor). Best-effort.
    let serverOk = false;
    if (branchId && terminalId) {
      try {
        await fireOpenOrder({
          client_uuid: st.clientUuid,
          terminal: terminalId,
          branch: branchId,
          order_type: st.orderType,
          table: st.tableId,
          covers: st.covers,
          buyer_name: st.customer?.name ?? null,
          buyer_phone: st.customer?.phone ?? null,
          cart_discount_pct: st.cartDiscountPct,
          // Send ALL lines so the server snapshot is the full order (KDS shows
          // everything); the KOT below prints only the new ones.
          cart_lines: lines.map((l) => ({
            product: l.product_id,
            quantity: l.quantity,
            unit_price: l.unit_price,
            discount_pct: l.discount_pct,
            discount_amount: l.discount_amount,
            tax_rate: l.tax_rate,
            is_taxable: l.is_taxable,
            modifiers: l.modifiers ?? [],
            item_note: l.item_note ?? null,
            course: l.course ?? null,
          })),
        });
        serverOk = true;
      } catch {
        /* offline / server error — fall through to print + local mark */
      }
    }

    // 2) Print the KOT for the newly-added lines.
    let printOk = false;
    try {
      const now = new Date();
      const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
      const res = await window.api.printer.printKOT({
        order_number: orderNumber,
        order_type: st.orderType ?? "dine_in",
        table_name: st.tableName,
        covers: st.covers,
        time,
        items: unsent.map((l) => ({
          product_name: l.product_name,
          quantity: l.quantity,
          modifiers: (l.modifiers ?? []).map((m) => ({ name: m.name })),
          item_note: l.item_note ?? null,
        })),
        width: 48,
      });
      printOk = res.success;
    } catch {
      /* printer error — KOT goes to disk via the main process fallback */
    }

    // 3) Mark fired locally regardless (the ticket exists; avoid double-fire).
    unsent.forEach((l) => updateLine(l.id, { sent_to_kitchen: true }));

    if (serverOk && printOk) {
      toast.show({ message: `Sent ${unsent.length} item(s) to the kitchen.`, variant: "success" });
    } else if (serverOk) {
      toast.show({ message: "Order sent to kitchen screen; KOT saved to disk (printer issue).", variant: "warning" });
    } else if (printOk) {
      toast.show({ message: "KOT printed; kitchen screen will update on next sync (offline).", variant: "warning" });
    } else {
      toast.show({ message: "Sent (offline) — KOT saved to disk; will sync later.", variant: "warning" });
    }
    setBusy(false);
  }

  return (
    <Button type="button" variant="outline" className="w-full gap-2" loading={busy} onClick={fire}>
      <ChefHat className="h-4 w-4" />
      Send to kitchen{unsent.length > 0 ? ` (${unsent.length})` : ""}
    </Button>
  );
}
