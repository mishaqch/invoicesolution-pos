/**
 * Restaurant order context bar — shown on the sale screen ONLY for restaurant
 * tenants. Lets the cashier set order type (dine-in / takeaway / delivery) and,
 * for dine-in, pick a table + covers. Stored on the sale store and carried into
 * the held order + checkout payload.
 */

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore, type OrderType } from "@/stores/sale";
import { OpenOrdersPanel } from "./OpenOrdersPanel";

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
  const setCustomer = useSaleStore((s) => s.setCustomer);
  const toast = useToast();

  const [tables, setTables] = useState<TableRow[]>([]);
  const [picking, setPicking] = useState(false);
  const [showOrders, setShowOrders] = useState(false);
  const [custName, setCustName] = useState("");
  const [custPhone, setCustPhone] = useState("");
  const [custAddr, setCustAddr] = useState("");

  // Default to dine-in on first mount so the cashier always has a context.
  useEffect(() => {
    if (!orderType) setOrderContext({ orderType: "dine_in" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // For takeaway/delivery, mirror the typed name/phone/address onto the sale's
  // customer so it flows to the order + receipt. A walk-in (unregistered) buyer.
  function pushCustomer(name: string, phone: string, addr: string) {
    if (!name && !phone && !addr) { setCustomer(null); return; }
    setCustomer({
      id: "",
      name: name || "Walk-in",
      phone: phone || null,
      cnic: null,
      ntn: null,
      registration_type: "unregistered",
      province: null,
      ...(addr ? { address: addr } : {}),
    } as never);
  }

  async function loadTables() {
    try {
      // Use the shared api() helper (resolves base URL + bearer token the same
      // way as login/catalog) instead of a hand-rolled fetch on VITE_API_URL —
      // the latter silently failed (empty base → relative URL) leaving the
      // picker blank. Branch filter is optional: if the cashier's branch has no
      // tables we still fall back to all of the tenant's tables.
      const path = `/restaurant/tables/${branchId ? `?branch=${branchId}` : ""}`;
      const data = await api<{ results?: TableRow[] } | TableRow[]>(path);
      let rows = (Array.isArray(data) ? data : data.results) ?? [];
      if (rows.length === 0 && branchId) {
        const all = await api<{ results?: TableRow[] } | TableRow[]>("/restaurant/tables/");
        rows = (Array.isArray(all) ? all : all.results) ?? [];
      }
      setTables(rows);
      if (rows.length === 0) {
        toast.show({ message: "No tables found for this account. Add tables in admin → Restaurant → Tables.", variant: "warning" });
      }
    } catch (err) {
      // Surface the failure instead of silently showing an empty picker.
      toast.show({
        message: `Could not load tables: ${err instanceof Error ? err.message : "network error"}`,
        variant: "destructive",
      });
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

      {/* Takeaway / delivery: capture the customer so we can call + (delivery) deliver. */}
      {(orderType === "takeaway" || orderType === "delivery") && (
        <div className="ml-2 flex flex-1 items-center gap-2">
          <input
            value={custName}
            onChange={(e) => { setCustName(e.target.value); pushCustomer(e.target.value, custPhone, custAddr); }}
            placeholder="Customer name"
            className="h-8 w-36 rounded-md border bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            value={custPhone}
            onChange={(e) => { setCustPhone(e.target.value); pushCustomer(custName, e.target.value, custAddr); }}
            placeholder="Phone"
            inputMode="tel"
            className="h-8 w-32 rounded-md border bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          {orderType === "delivery" && (
            <input
              value={custAddr}
              onChange={(e) => { setCustAddr(e.target.value); pushCustomer(custName, custPhone, e.target.value); }}
              placeholder="Delivery address"
              className="h-8 flex-1 rounded-md border bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          )}
        </div>
      )}

      {/* Open-orders book — resume a parked table/order. */}
      <button
        type="button"
        onClick={() => setShowOrders(true)}
        className="ml-auto rounded-md border px-3 py-1.5 font-medium hover:bg-accent"
      >
        Open orders
      </button>
      {showOrders && <OpenOrdersPanel branchId={branchId} onClose={() => setShowOrders(false)} />}
    </div>
  );
}
