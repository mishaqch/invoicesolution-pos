/**
 * "Send to kitchen" button — fires the not-yet-sent cart lines (server open
 * order + KOT) via the shared fireUnsentToKitchen helper. Restaurant tenants
 * only. The same fire logic also runs automatically on Charge (payment.tsx).
 *
 * After a successful send the order now lives in the server "Open orders" book,
 * so we CLEAR the front screen (reset the cart) so the cashier can immediately
 * start the next order. The parked order is resumed later from "Open orders"
 * and charged there. We only clear when the server actually accepted the order
 * (serverOk) — if the server call failed, the order is NOT in Open orders, so
 * clearing would lose the cart; in that case we keep the cart for a retry.
 */

import { ChefHat } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useTextPrompt } from "@/components/ui/TextPromptModal";
import { useSaleStore } from "@/stores/sale";
import { fireUnsentToKitchen } from "./fire";

export function SendToKitchen({
  branchId,
  terminalId,
}: {
  branchId: string | null;
  terminalId: string | null;
}) {
  const lines = useSaleStore((s) => s.lines);
  const toast = useToast();
  const prompt = useTextPrompt();
  const [busy, setBusy] = useState(false);

  const unsentCount = lines.filter((l) => !l.sent_to_kitchen).length;

  async function fire() {
    if (unsentCount === 0) {
      toast.show({ message: "Nothing new to send — all items already in the kitchen.", variant: "warning" });
      return;
    }

    // Ask for a name/reference (like Save order) so the kitchen order is
    // recognisable in Open orders — unless it already has one (resumed order).
    const st0 = useSaleStore.getState();
    if (!st0.heldLabel) {
      const suggested = st0.tableName ? `Table ${st0.tableName}` : "";
      const label = await prompt({
        title: "Send to kitchen",
        description: "Add a reference so you can find this order in Open orders (e.g. customer name or table).",
        placeholder: "e.g. Ahmed / Table 5 / red shirt guy",
        initialValue: suggested,
        confirmLabel: "Send to kitchen",
      });
      if (label === null) return; // cancelled
      if (!label.trim()) {
        toast.show({ message: "A reference is required to send the order.", variant: "warning" });
        return;
      }
      useSaleStore.getState().setHeldLabel(label.trim());
    }

    setBusy(true);
    const r = await fireUnsentToKitchen({ branchId, terminalId });
    if (r.serverOk && r.printOk) {
      toast.show({ message: `Sent ${r.fired} item(s) to the kitchen — order parked in Open orders.`, variant: "success" });
    } else if (r.serverOk) {
      toast.show({ message: "Order parked in Open orders; KOT saved to disk (printer issue).", variant: "warning" });
    } else if (r.printOk) {
      toast.show({ message: `KOT printed, but kitchen screen NOT updated: ${r.serverErr ?? "server error"}. Cart kept — try again.`, variant: "destructive" });
    } else {
      toast.show({ message: `Could not send to kitchen: ${r.serverErr ?? "unknown error"}. Cart kept — try again.`, variant: "destructive" });
    }
    // Order is now in the server Open-orders book → clear the front screen for
    // the next order. Only when the server accepted it (otherwise keep the cart
    // so nothing is lost and the cashier can retry).
    if (r.serverOk) {
      const st = useSaleStore.getState();
      st.resetForNewSale();
      st.setStage("empty");
    }
    setBusy(false);
  }

  return (
    <Button type="button" variant="outline" className="w-full gap-2" disabled={busy} onClick={fire}>
      <ChefHat className="h-4 w-4" />
      {busy ? "Sending…" : `Send to kitchen${unsentCount > 0 ? ` (${unsentCount})` : ""}`}
    </Button>
  );
}
