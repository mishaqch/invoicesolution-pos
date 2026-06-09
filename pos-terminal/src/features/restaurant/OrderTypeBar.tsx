/**
 * Restaurant order context bar — shown on the sale screen ONLY for restaurant
 * tenants. Lets the cashier set order type (dine-in / takeaway / delivery) and,
 * for dine-in, pick a table + covers. Stored on the sale store and carried into
 * the held order + checkout payload.
 */

import { useEffect, useState } from "react";

import { useSaleStore, type OrderType } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";

interface TableRow { id: string; name: string; seats: number }

const TYPES: { value: OrderType; label: string }[] = [
  { value: "dine_in", label: "Dine-in" },
  { value: "takeaway", label: "Takeaway" },
  { value: "delivery", label: "Delivery" },
];

export function OrderTypeBar({ branchId }: { branchId: string | null }) {
  const orderType = useSaleStore((s) => s.orderType);
  const tableName = useSaleStore((s) => s.tableName);
  const setOrderContext = useSaleStore((s) => s.setOrderContext);
  const access = useSessionStore((s) => s.access);

  const [tables, setTables] = useState<TableRow[]>([]);
  const [picking, setPicking] = useState(false);

  // Default to dine-in on first mount so the cashier always has a context.
  useEffect(() => {
    if (!orderType) setOrderContext({ orderType: "dine_in" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadTables() {
    try {
      const base = (import.meta as { env?: Record<string, string> }).env?.VITE_API_URL ?? "";
      const url = `${base}/api/restaurant/tables/${branchId ? `?branch=${branchId}` : ""}`;
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${access}` } });
      if (resp.ok) {
        const data = await resp.json();
        setTables((data.results ?? data) as TableRow[]);
      }
    } catch {
      /* offline — table picker just shows nothing; cashier can still proceed */
    }
  }

  return (
    <div className="flex items-center gap-2 border-b bg-muted/30 px-3 py-2 text-sm">
      <div className="flex gap-1">
        {TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setOrderContext({ orderType: t.value, tableId: null, tableName: null })}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              orderType === t.value ? "bg-primary text-primary-foreground" : "bg-background hover:bg-accent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {orderType === "dine_in" && (
        <div className="ml-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => { setPicking((p) => !p); if (tables.length === 0) void loadTables(); }}
            className="rounded-md border px-3 py-1.5 hover:bg-accent"
          >
            {tableName ? `Table ${tableName}` : "Pick table"}
          </button>
          {picking && (
            <div className="absolute z-30 mt-24 grid max-h-64 grid-cols-4 gap-1 overflow-auto rounded-md border bg-popover p-2 shadow-lg">
              {tables.length === 0 ? (
                <span className="col-span-4 p-2 text-xs text-muted-foreground">No tables (or offline).</span>
              ) : tables.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => { setOrderContext({ orderType: "dine_in", tableId: t.id, tableName: t.name }); setPicking(false); }}
                  className="rounded-md border px-3 py-2 text-center hover:bg-accent"
                >
                  <div className="font-semibold">{t.name}</div>
                  <div className="text-[10px] text-muted-foreground">{t.seats} seats</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
