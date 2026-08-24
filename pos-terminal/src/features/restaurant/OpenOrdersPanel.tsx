/**
 * Open-orders panel — the table/order book on the terminal. Lists every open
 * (held, fired) restaurant order on the server so a cashier can resume Table 3
 * while Table 1 is still cooking. Tapping an order rebuilds the cart from the
 * server snapshot (lines + modifiers + restaurant context) so the cashier can
 * add a course, re-fire, or Charge.
 */

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore, type CartLine, type OrderType } from "@/stores/sale";
import { getOpenOrder, listOpenOrders, type OpenOrderSummary } from "./api";

export function OpenOrdersPanel({
  branchId,
  onClose,
}: {
  branchId: string | null;
  onClose: () => void;
}) {
  const [orders, setOrders] = useState<OpenOrderSummary[] | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const loadFromHold = useSaleStore((s) => s.loadFromHold);
  const toast = useToast();

  // Load on open, then poll every few seconds while the panel is open, so an
  // order that was just paid (its held row finalized server-side, is_held=False)
  // drops off the list on its own — the cashier never sees a stale paid order.
  useEffect(() => {
    let alive = true;
    const load = () =>
      listOpenOrders(branchId)
        .then((d) => {
          if (alive) setOrders(d.orders);
        })
        .catch(() => {
          if (alive) setOrders((prev) => prev ?? []);
        });
    void load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [branchId]);

  async function resume(id: string) {
    setLoadingId(id);
    try {
      const o = await getOpenOrder(id);
      const lines: CartLine[] = o.cart_lines.map((l) => ({
        id: crypto.randomUUID(),
        product_id: l.product,
        product_name: l.product_name,
        product_sku: l.product_sku,
        uom_code: l.uom_code,
        hs_code: l.hs_code,
        quantity: l.quantity,
        unit_price: l.unit_price,
        discount_pct: l.discount_pct,
        discount_amount: l.discount_amount,
        tax_rate: l.tax_rate,
        is_taxable: Number(l.tax_rate) > 0,
        modifiers: l.modifiers,
        item_note: l.item_note,
        course: l.course,
        // Already fired — so re-fire only prints newly-added lines.
        sent_to_kitchen: l.sent_to_kitchen,
      }));
      loadFromHold({
        clientUuid: o.client_uuid,
        lines,
        customer: null,
        cartDiscountPct: "0",
        orderType: (o.order_type as OrderType) ?? null,
        tableId: o.table_id,
        tableName: o.table,
        covers: o.covers,
        // Resuming a server OPEN order → emptying the cart should void it.
        resumedOpenOrder: true,
        // Carry the reference so a follow-up KOT shows the name, not a hex id.
        heldLabel: o.held_label,
      });
      toast.show({
        message: `Resumed ${o.table ? `Table ${o.table}` : o.order_type}.`,
        variant: "success",
      });
      onClose();
    } catch {
      toast.show({ message: "Could not load that order (offline?).", variant: "destructive" });
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg bg-background p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Open orders</h2>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
        {orders === null ? (
          <p className="p-4 text-sm text-muted-foreground">Loading…</p>
        ) : orders.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">
            No open orders. Start one above.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2 overflow-auto sm:grid-cols-3">
            {orders.map((o) => (
              <button
                key={o.id}
                type="button"
                disabled={loadingId !== null}
                onClick={() => resume(o.id)}
                className="rounded-md border p-3 text-left transition-colors hover:bg-accent disabled:opacity-50"
              >
                <div className="font-semibold">
                  {o.table ? `Table ${o.table}` : o.held_label || (o.order_type ?? "Order")}
                </div>
                {/* Show the cashier's reference as a subtitle when it isn't
                    already the headline (i.e. a dine-in order WITH a table). */}
                {o.held_label && o.table && (
                  <div className="truncate text-xs font-medium text-foreground">{o.held_label}</div>
                )}
                {/* Status badge: clearly shows whether the order is just SAVED
                    (not sent) or already IN KITCHEN (fired) / ready / served. */}
                <div className="mt-1 flex items-center gap-1.5">
                  <span className={statusBadgeClass(o.order_status)}>
                    {statusLabel(o.order_status)}
                  </span>
                  <span className="text-xs text-muted-foreground">{o.items.length} item(s)</span>
                </div>
                <div className="mt-1 font-mono text-sm">Rs. {trim(o.grand_total)}</div>
                {loadingId === o.id && (
                  <div className="text-[10px] text-muted-foreground">Loading…</div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function statusLabel(s: string | null): string {
  switch (s) {
    case "sent_to_kitchen":
      return "In kitchen";
    case "ready":
      return "Ready";
    case "served":
      return "Served";
    default:
      return "Saved"; // saved/parked, not yet sent to the kitchen
  }
}

/** Colour the status badge so the state reads at a glance:
 *  amber = just saved, blue = in kitchen, green = ready/served. */
function statusBadgeClass(s: string | null): string {
  const base = "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide";
  switch (s) {
    case "sent_to_kitchen":
      return `${base} bg-primary/15 text-primary`;
    case "ready":
    case "served":
      return `${base} bg-success-soft text-success-soft-foreground`;
    default:
      return `${base} bg-warning-soft text-warning-soft-foreground`;
  }
}
function trim(s: string): string {
  const n = Number(s);
  return Number.isFinite(n) ? n.toFixed(2) : s;
}
