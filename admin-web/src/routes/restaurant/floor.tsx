import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn, money } from "@/lib/utils";
import { useFloor, type FloorTable } from "@/lib/queries";

const STATUS_STYLE: Record<string, string> = {
  open: "border-info-soft bg-info-soft/30",
  sent_to_kitchen: "border-warning bg-warning/10",
  ready: "border-success bg-success/10",
  served: "border-muted bg-muted/30",
};

export default function FloorView() {
  const { data, isLoading } = useFloor();
  const tables = data?.tables ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Floor</h1>
        <p className="text-sm text-muted-foreground">
          Live table map — free, occupied, and order status. Refreshes automatically.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : tables.length === 0 ? (
        <div className="rounded-md border py-10 text-center text-muted-foreground">
          No tables defined. Add tables under Restaurant → Tables.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {tables.map((t) => <TableCard key={t.id} t={t} />)}
        </div>
      )}
    </div>
  );
}

function TableCard({ t }: { t: FloorTable }) {
  const occupied = Boolean(t.order);
  const status = t.order?.order_status ?? "free";
  return (
    <div className={cn(
      "rounded-lg border p-3 transition-colors",
      occupied ? STATUS_STYLE[status] ?? "border-warning bg-warning/10" : "border-dashed",
    )}>
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
