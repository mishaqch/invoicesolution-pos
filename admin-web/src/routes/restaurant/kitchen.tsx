import { ChefHat, Clock } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { ApiError } from "@/lib/api";
import { useKds, useOrderAction, type OrderView } from "@/lib/queries";

export default function KitchenDisplay() {
  const { data, isLoading, error } = useKds();
  const action = useOrderAction();
  const orders = data?.orders ?? [];
  const [notice, setNotice] = useState<string | null>(null);

  function act(id: string, op: "ready" | "served") {
    setNotice(null);
    action.mutate({ id, op }, {
      onError: (err) => {
        // 404 just means the order was already paid/removed (a stale card from
        // the 5s poll). Don't alarm the kitchen — note it and let the auto
        // refetch (onSettled) drop the card.
        if (err instanceof ApiError && err.status === 404) {
          setNotice("That order was already cleared — refreshing.");
        } else {
          setNotice(`Couldn't update the order: ${err instanceof Error ? err.message : "error"}.`);
        }
      },
    });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Kitchen"
        subtitle="Live order queue. Mark orders ready when plated, served when handed off. Refreshes automatically."
      />

      {notice && (
        <div className="rounded-md border border-warning bg-warning/10 px-3 py-2 text-sm text-warning-soft-foreground">
          {notice}
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <div className="rounded-md border border-destructive bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Couldn't load the kitchen queue ({error instanceof ApiError ? `HTTP ${error.status}` : "network error"}).
          It will retry automatically.
        </div>
      ) : orders.length === 0 ? (
        <div className="rounded-md border py-12 text-center text-muted-foreground">
          <ChefHat className="mx-auto mb-2 h-7 w-7 opacity-50" />
          No orders in the kitchen right now.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {orders.map((o) => (
            <OrderTicket key={o.id} o={o} onAction={(op) => act(o.id, op)} busy={action.isPending} />
          ))}
        </div>
      )}
    </div>
  );
}

function OrderTicket({
  o, onAction, busy,
}: {
  o: OrderView;
  onAction: (op: "ready" | "served") => void;
  busy: boolean;
}) {
  const ready = o.order_status === "ready";
  return (
    <div className={`flex flex-col rounded-lg border-2 p-3 ${ready ? "border-success bg-success/5" : "border-warning bg-warning/5"}`}>
      <div className="flex items-center justify-between">
        <span className="font-semibold">
          {o.table ? `Table ${o.table}` : o.order_type}
        </span>
        <Badge variant={ready ? "default" : "warning"} className="text-[10px]">
          {ready ? "Ready" : "Cooking"}
        </Badge>
      </div>
      <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
        <Clock className="h-3 w-3" />
        #{o.local_invoice_number}
        {o.covers ? ` · ${o.covers} covers` : ""}
      </div>

      <ul className="mt-2 flex-1 space-y-1.5 text-sm">
        {o.items.filter((it) => !it.is_cancelled).map((it, i) => (
          <li key={i}>
            <div className="font-medium">{trimQty(it.quantity)}× {it.name}</div>
            {it.modifiers.length > 0 && (
              <div className="pl-3 text-xs text-muted-foreground">
                {it.modifiers.map((m) => m.name).join(", ")}
              </div>
            )}
            {it.item_note && <div className="pl-3 text-xs italic text-warning-soft-foreground">“{it.item_note}”</div>}
          </li>
        ))}
      </ul>

      <div className="mt-3 flex gap-2">
        {!ready ? (
          <Button size="sm" className="flex-1" loading={busy} onClick={() => onAction("ready")}>Mark ready</Button>
        ) : (
          <Button size="sm" variant="outline" className="flex-1" loading={busy} onClick={() => onAction("served")}>Served</Button>
        )}
      </div>
    </div>
  );
}

function trimQty(s: string): string {
  const n = Number(s);
  return Number.isFinite(n) ? String(n) : s;
}
