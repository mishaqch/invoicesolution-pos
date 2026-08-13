/**
 * Restaurant order context bar — shown on the sale screen ONLY for restaurant
 * tenants. Lets the cashier set order type (dine-in / takeaway / delivery) and,
 * for dine-in, pick a table + covers. Stored on the sale store and carried into
 * the held order + checkout payload.
 */

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useToast } from "@/components/feedback/Toast";
import { useSaleStore, type OrderType } from "@/stores/sale";
import { OpenOrdersPanel } from "./OpenOrdersPanel";

interface TableRow { id: string; name: string; seats: number }
// The floor endpoint returns each table plus its open order (null = free).
interface FloorTable { id: string; name: string; seats: number; order: unknown | null }

const TYPES: { value: OrderType; label: string }[] = [
  { value: "dine_in", label: "Dine-in" },
  { value: "takeaway", label: "Takeaway" },
  { value: "delivery", label: "Delivery" },
];

export function OrderTypeBar({ branchId }: { branchId: string | null }) {
  const orderType = useSaleStore((s) => s.orderType);
  const tableName = useSaleStore((s) => s.tableName);
  const tableId = useSaleStore((s) => s.tableId);
  const setOrderContext = useSaleStore((s) => s.setOrderContext);
  const setCustomer = useSaleStore((s) => s.setCustomer);
  const toast = useToast();

  const [tables, setTables] = useState<TableRow[]>([]);
  const [picking, setPicking] = useState(false);
  const [showOrders, setShowOrders] = useState(false);
  const [custName, setCustName] = useState("");
  const [custPhone, setCustPhone] = useState("");
  const [custAddr, setCustAddr] = useState("");
  // Wraps the "Pick table" button + its dropdown, so a click anywhere OUTSIDE
  // this box (a misclick by the waiter) closes the picker.
  const tablePickerRef = useRef<HTMLDivElement>(null);

  // Default to dine-in on first mount so the cashier always has a context.
  useEffect(() => {
    if (!orderType) setOrderContext({ orderType: "dine_in" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Close the table picker on an outside click or Escape — the waiter may have
  // opened it by mistake and just wants it to go away without selecting a table.
  useEffect(() => {
    if (!picking) return;
    function onDown(e: MouseEvent) {
      if (tablePickerRef.current && !tablePickerRef.current.contains(e.target as Node)) {
        setPicking(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setPicking(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [picking]);

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
      // Use the FLOOR endpoint (not the plain tables list) so we know which
      // tables are AVAILABLE: it returns each table plus its open order (null =
      // free). We show only the free ones — a table that already has an open
      // order shouldn't be selectable for a new order. The currently-selected
      // table is always kept in the list so the cashier can see/keep their pick.
      // Uses the shared api() helper (resolves base URL + bearer token the same
      // way as login/catalog). Branch filter is optional.
      const path = `/restaurant/floor/${branchId ? `?branch=${branchId}` : ""}`;
      const data = await api<{ tables?: FloorTable[] }>(path);
      const all = data.tables ?? [];
      const available = all.filter((t) => t.order == null || t.id === tableId);
      const rows: TableRow[] = available.map((t) => ({ id: t.id, name: t.name, seats: t.seats }));
      setTables(rows);
      if (all.length === 0) {
        toast.show({ message: "No tables found for this account. Add tables in admin → Restaurant → Tables.", variant: "warning" });
      } else if (rows.length === 0) {
        toast.show({ message: "All tables are occupied right now. Free one from Open orders (charge/close it) to reuse it.", variant: "warning" });
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
              orderType === t.value ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {orderType === "dine_in" && (
        <div ref={tablePickerRef} className="relative ml-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              // Always reload on open so occupancy is fresh — a table freed or
              // taken since last time is reflected right away.
              setPicking((p) => {
                if (!p) void loadTables();
                return !p;
              });
            }}
            className="rounded-md border px-3 py-1.5 hover:bg-muted"
          >
            {tableName ? `Table ${tableName}` : "Pick table"}
          </button>
          {picking && (
            // bg-background (white) + border — the terminal theme defines no
            // --popover/--accent tokens, so the old bg-popover / hover:bg-accent
            // rendered transparent. Use defined tokens (bg-background/bg-muted).
            <div className="absolute left-0 top-full z-30 mt-1 grid max-h-64 w-72 grid-cols-4 gap-1.5 overflow-auto rounded-md border bg-background p-2 shadow-lg">
              {tables.length === 0 ? (
                <span className="col-span-4 p-2 text-xs text-muted-foreground">No tables (or offline).</span>
              ) : tables.map((t) => {
                const active = tableId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => { setOrderContext({ orderType: "dine_in", tableId: t.id, tableName: t.name }); setPicking(false); }}
                    className={`rounded-md border px-3 py-2 text-center transition-colors ${
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-input bg-muted hover:bg-primary/10 hover:border-primary"
                    }`}
                  >
                    <div className="font-semibold">{t.name}</div>
                    <div className={`text-[10px] ${active ? "text-primary-foreground/80" : "text-muted-foreground"}`}>{t.seats} seats</div>
                  </button>
                );
              })}
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
        className="ml-auto rounded-md border px-3 py-1.5 font-medium hover:bg-muted"
      >
        Open orders
      </button>
      {showOrders && <OpenOrdersPanel branchId={branchId} onClose={() => setShowOrders(false)} />}
    </div>
  );
}
