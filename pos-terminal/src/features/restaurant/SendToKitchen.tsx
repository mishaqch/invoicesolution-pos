/**
 * "Send to kitchen" — prints a KOT for the not-yet-fired cart lines and marks
 * them fired, so re-firing (course 2) only prints newly-added items. Restaurant
 * tenants only. Offline-safe: the KOT prints from local cart state; the kitchen
 * never waits on the network. The order is finalized to FBR later at Charge.
 */

import { ChefHat } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore } from "@/stores/sale";

export function SendToKitchen({ orderNumber }: { orderNumber: string }) {
  const lines = useSaleStore((s) => s.lines);
  const orderType = useSaleStore((s) => s.orderType);
  const tableName = useSaleStore((s) => s.tableName);
  const covers = useSaleStore((s) => s.covers);
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
    try {
      const now = new Date();
      const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
      const res = await window.api.printer.printKOT({
        order_number: orderNumber,
        order_type: orderType ?? "dine_in",
        table_name: tableName,
        covers,
        time,
        items: unsent.map((l) => ({
          product_name: l.product_name,
          quantity: l.quantity,
          modifiers: (l.modifiers ?? []).map((m) => ({ name: m.name })),
          item_note: l.item_note ?? null,
        })),
        width: 48,
      });
      // Mark fired regardless of printer outcome — a disk fallback still counts
      // as "sent" (the ticket exists); re-firing would double-print.
      unsent.forEach((l) => updateLine(l.id, { sent_to_kitchen: true }));
      if (res.success) {
        toast.show({ message: `Sent ${unsent.length} item(s) to the kitchen.`, variant: "success" });
      } else {
        toast.show({ message: `KOT not printed (${res.reason}); saved to disk.`, variant: "warning" });
      }
    } catch (err) {
      toast.show({ message: `Could not send to kitchen: ${err}`, variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button type="button" variant="outline" className="w-full gap-2" loading={busy} onClick={fire}>
      <ChefHat className="h-4 w-4" />
      Send to kitchen{unsent.length > 0 ? ` (${unsent.length})` : ""}
    </Button>
  );
}
