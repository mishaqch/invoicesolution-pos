/**
 * "Save order" button — parks the current cart in the server "Open orders" book
 * WITHOUT alerting the kitchen (no KOT, no KDS). Restaurant tenants only.
 *
 * This is the top-POS "Save/Send" action: it lets the cashier step away to
 * another table before the customer has finalised. On success the front screen
 * is cleared for the next order; the parked order is resumed later from
 * "Open orders" (where it can be edited, sent to the kitchen, or charged).
 *
 * Contrast with Send to kitchen, which ALSO fires the food (KOT + KDS).
 */

import { Bookmark } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore } from "@/stores/sale";
import { saveOpenOrder } from "./fire";

export function SaveOrder({
  branchId,
  terminalId,
}: {
  branchId: string | null;
  terminalId: string | null;
}) {
  const lines = useSaleStore((s) => s.lines);
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function save() {
    if (lines.length === 0) {
      toast.show({ message: "Nothing to save — the cart is empty.", variant: "warning" });
      return;
    }
    setBusy(true);
    const r = await saveOpenOrder({ branchId, terminalId });
    if (r.serverOk) {
      toast.show({ message: "Order saved to Open orders (kitchen not notified).", variant: "success" });
      // Parked on the server → clear the front screen for the next order.
      const st = useSaleStore.getState();
      st.resetForNewSale();
      st.setStage("empty");
    } else {
      // Keep the cart so nothing is lost; the cashier can retry.
      toast.show({ message: `Could not save the order: ${r.serverErr ?? "unknown error"}. Cart kept — try again.`, variant: "destructive" });
    }
    setBusy(false);
  }

  return (
    <Button type="button" variant="outline" className="w-full gap-2" disabled={busy} onClick={save}>
      <Bookmark className="h-4 w-4" />
      {busy ? "Saving…" : "Save order"}
    </Button>
  );
}
