/**
 * "Send to kitchen" button — fires the not-yet-sent cart lines (server open
 * order + KOT) via the shared fireUnsentToKitchen helper. Restaurant tenants
 * only. The same fire logic also runs automatically on Charge (payment.tsx).
 */

import { ChefHat } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
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
  const [busy, setBusy] = useState(false);

  const unsentCount = lines.filter((l) => !l.sent_to_kitchen).length;

  async function fire() {
    if (unsentCount === 0) {
      toast.show({ message: "Nothing new to send — all items already in the kitchen.", variant: "warning" });
      return;
    }
    setBusy(true);
    const r = await fireUnsentToKitchen({ branchId, terminalId });
    if (r.serverOk && r.printOk) {
      toast.show({ message: `Sent ${r.fired} item(s) to the kitchen.`, variant: "success" });
    } else if (r.serverOk) {
      toast.show({ message: "Order on the kitchen screen; KOT saved to disk (printer issue).", variant: "warning" });
    } else if (r.printOk) {
      toast.show({ message: `KOT printed, but kitchen screen NOT updated: ${r.serverErr ?? "server error"}.`, variant: "destructive" });
    } else {
      toast.show({ message: `Could not send to kitchen: ${r.serverErr ?? "unknown error"}.`, variant: "destructive" });
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
