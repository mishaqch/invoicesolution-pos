import { Users } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { cn, money } from "@/lib/utils";
import { useFloor, type FloorTable, type OrderView } from "@/lib/queries";

const STATUS_STYLE: Record<string, string> = {
  open: "border-info-soft bg-info-soft/30",
  sent_to_kitchen: "border-warning bg-warning/10",
  ready: "border-success bg-success/10",
  served: "border-muted bg-muted/30",
};

export default function FloorView() {
  const { data, isLoading } = useFloor();
  const tables = data?.tables ?? [];
  const [viewing, setViewing] = useState<OrderView | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Floor"
        subtitle="Live table map — free, occupied, and order status. Tap an occupied table to view its bill. Refreshes automatically."
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : tables.length === 0 ? (
        <div className="rounded-md border py-10 text-center text-muted-foreground">
          No tables defined. Add tables under Restaurant → Tables.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {tables.map((t) => (
            <TableCard key={t.id} t={t} onView={() => t.order && setViewing(t.order)} />
          ))}
        </div>
      )}

      {viewing && <BillModal order={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

function TableCard({ t, onView }: { t: FloorTable; onView: () => void }) {
  const occupied = Boolean(t.order);
  const status = t.order?.order_status ?? "free";
  return (
    <div
      onClick={occupied ? onView : undefined}
      className={cn(
        "rounded-lg border p-3 transition-colors",
        occupied ? STATUS_STYLE[status] ?? "border-warning bg-warning/10" : "border-dashed",
        occupied && "cursor-pointer hover:ring-2 hover:ring-primary/40",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-lg font-semibold">{t.name}</span>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Users className="h-3 w-3" />{t.seats}
        </span>
      </div>
      {t.zone && <div className="text-[11px] text-muted-foreground">{t.zone}</div>}
      {occupied ? (
        <div className="mt-2 space-y-1">
          <Badge variant={status === "ready" ? "default" : "warning"} className="text-[10px]">
            {labelFor(status)}
          </Badge>
          <div className="text-xs text-muted-foreground">
            {t.order!.order_type} · {t.order!.items.length} item(s)
          </div>
          <div className="font-mono text-sm">Rs. {money(t.order!.grand_total)}</div>
        </div>
      ) : (
        <div className="mt-2 text-xs text-muted-foreground">Free</div>
      )}
    </div>
  );
}

function labelFor(status: string | null): string {
  switch (status) {
    case "sent_to_kitchen": return "In kitchen";
    case "ready": return "Ready";
    case "served": return "Served";
    default: return "Open";
  }
}

function BillModal({ order, onClose }: { order: OrderView; onClose: () => void }) {
  const items = order.items.filter((it) => !it.is_cancelled);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>{order.table ? `Table ${order.table}` : order.order_type}</span>
            <Badge variant={order.order_status === "ready" ? "default" : "warning"} className="text-[10px]">
              {labelFor(order.order_status)}
            </Badge>
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            #{order.local_invoice_number}{order.covers ? ` · ${order.covers} covers` : ""}
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <ul className="space-y-1.5 text-sm">
            {items.map((it, i) => (
              <li key={i} className="flex justify-between">
                <span>
                  {trimQty(it.quantity)}× {it.name}
                  {it.modifiers.length > 0 && (
                    <span className="block pl-3 text-xs text-muted-foreground">
                      {it.modifiers.map((m) => m.name).join(", ")}
                    </span>
                  )}
                  {it.item_note && <span className="block pl-3 text-xs italic text-muted-foreground">“{it.item_note}”</span>}
                </span>
              </li>
            ))}
          </ul>
          <div className="flex justify-between border-t pt-2 font-medium">
            <span>Total</span>
            <span className="font-mono">Rs. {money(order.grand_total)}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Take payment at the POS terminal (resume this table, then Charge) to finalize + send to FBR.
          </p>
          <div className="flex justify-end">
            <Button variant="outline" onClick={onClose}>Close</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function trimQty(s: string): string {
  const n = Number(s);
  return Number.isFinite(n) ? String(n) : s;
}
