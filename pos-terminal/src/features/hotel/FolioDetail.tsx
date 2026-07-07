/** A folio's running tab — view charges, add today's charges, checkout. */
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";
import { ProductGrid } from "@/features/sale/ProductGrid";
import { ApiError } from "@/lib/api";
import { rs } from "@/lib/money";
import { useSessionStore } from "@/stores/session";

import {
  addCharge,
  checkoutFolio,
  getFolio,
  removeCharge,
  removeItem,
  type ChargeLine,
  type FolioBill,
} from "@/features/hotel/api";
import type { CartLine } from "@/stores/sale";

function errMsg(e: unknown): string {
  if (e instanceof ApiError && e.data && typeof e.data === "object") {
    const d = e.data as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    for (const v of Object.values(d)) {
      if (Array.isArray(v) && typeof v[0] === "string") return v[0];
      if (typeof v === "string") return v;
    }
  }
  return "Something went wrong. Check your connection and try again.";
}

const PAYMENT_METHODS = ["cash", "card_credit", "easypaisa", "jazzcash", "bank_transfer"] as const;

export function FolioDetail({
  folioId,
  onBack,
  onCheckedOut,
}: {
  folioId: string;
  onBack: () => void;
  onCheckedOut: () => void;
}) {
  const toast = useToast();
  const tenant = useSessionStore((s) => s.tenant);
  const [bill, setBill] = useState<FolioBill | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"view" | "add" | "checkout">("view");

  // Local add-charge cart (kept separate from the main till's sale store).
  const [cart, setCart] = useState<CartLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [payMethod, setPayMethod] = useState<string>("cash");
  // Which room this batch of charges is tagged to ("" = whole stay / general).
  const [chargeRoom, setChargeRoom] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      setBill(await getFolio(folioId));
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folioId]);

  function addToCart(line: Omit<CartLine, "id">) {
    setCart((c) => {
      const idx = c.findIndex((l) => l.product_id === line.product_id);
      if (idx >= 0) {
        const next = [...c];
        next[idx] = { ...next[idx], quantity: String((Number(next[idx].quantity) || 0) + 1) };
        return next;
      }
      return [...c, { ...line, id: crypto.randomUUID() } as CartLine];
    });
  }

  const cartTotal = cart.reduce((acc, l) => {
    const net = (Number(l.quantity) || 0) * (Number(l.unit_price) || 0);
    const tax = l.is_taxable ? net * (Number(l.tax_rate) || 0) / 100 : 0;
    return acc + net + tax;
  }, 0);

  async function saveCharges() {
    if (cart.length === 0) return;
    setBusy(true);
    try {
      const lines: ChargeLine[] = cart.map((l) => ({
        product: l.product_id,
        quantity: l.quantity,
        unit_price: l.unit_price,
        tax_rate: l.tax_rate,
        is_taxable: l.is_taxable,
        discount_amount: l.discount_amount,
        item_note: l.item_note ?? null,
        modifiers: l.modifiers,
      }));
      const updated = await addCharge(folioId, lines, "restaurant", chargeRoom || null);
      setBill(updated);
      setCart([]);
      setChargeRoom("");
      setMode("view");
      toast.show({ message: "Charges added to folio.", variant: "success" });
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function doCheckout() {
    if (!bill) return;
    setBusy(true);
    try {
      const settled = await checkoutFolio(folioId, [
        { payment_method: payMethod, amount: bill.grand_total },
      ]);
      // Print the consolidated bill (non-fiscal for resort tenants).
      await window.api.printer
        .printFolio({
          business_name: tenant?.business_name ?? "Resort",
          ntn: tenant?.ntn ?? "",
          address: tenant?.address ?? undefined,
          contact: tenant?.phone ?? undefined,
          width: 48,
          is_fiscal: tenant?.fbr_connection_type !== "none",
          folio: settled,
        })
        .catch(() => {/* print failure shouldn't block checkout */});
      onCheckedOut();
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function voidItem(chargeId: string, itemId: string, name: string) {
    if (!confirm(`Remove "${name}" from the bill?`)) return;
    try {
      setBill(await removeItem(folioId, chargeId, itemId));
      toast.show({ message: "Item removed.", variant: "info" });
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    }
  }

  async function voidCharge(chargeId: string) {
    if (!confirm("Remove this entire charge entry from the bill?")) return;
    try {
      setBill(await removeCharge(folioId, chargeId));
      toast.show({ message: "Charge removed.", variant: "info" });
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    }
  }

  const isOpen = bill?.status === "open";

  if (loading || !bill) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading…</div>
    );
  }

  // --- ADD CHARGES (scoped till) ---
  if (mode === "add") {
    return (
      <div className="flex h-full flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
          <button type="button" onClick={() => { setCart([]); setMode("view"); }} className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted">
            <ArrowLeft className="h-4 w-4" /> Cancel
          </button>
          <div className="flex items-center gap-3">
            <div className="text-sm font-semibold">Add charges · {bill.guest.name}</div>
            {bill.rooms.length > 1 && (
              <select
                value={chargeRoom}
                onChange={(e) => setChargeRoom(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                title="Tag this charge to a room"
              >
                <option value="">Whole stay (no room)</option>
                {bill.rooms.map((r) => (
                  <option key={r.id} value={r.id}>Room {r.number}</option>
                ))}
              </select>
            )}
          </div>
          <Button size="sm" onClick={saveCharges} disabled={busy || cart.length === 0}>
            {busy ? "Saving…" : `Add ${cart.length} item${cart.length === 1 ? "" : "s"}`}
          </Button>
        </header>
        <div className="grid min-h-0 flex-1 grid-cols-[1fr_320px]">
          <div className="min-h-0 overflow-hidden border-r p-3">
            <ProductGrid onAdd={addToCart} />
          </div>
          <div className="flex min-h-0 flex-col">
            <div className="flex-1 overflow-auto p-3">
              {cart.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">Tap items to add to this guest's tab.</div>
              ) : (
                <div className="divide-y">
                  {cart.map((l) => (
                    <div key={l.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{l.product_name}</div>
                        <div className="text-xs text-muted-foreground">{l.quantity} × Rs {rs(l.unit_price)}</div>
                      </div>
                      <button type="button" onClick={() => setCart((c) => c.filter((x) => x.id !== l.id))} className="text-muted-foreground hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="border-t p-3 text-sm">
              <div className="flex justify-between font-semibold"><span>This charge</span><span className="font-mono">Rs {rs(cartTotal)}</span></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- VIEW + CHECKOUT ---
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <button type="button" onClick={onBack} className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted">
          <ArrowLeft className="h-4 w-4" /> Stays
        </button>
        <div className="text-sm font-semibold">{bill.guest.name} · {bill.room?.number ?? "—"}</div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setMode("add")}><Plus className="mr-1 h-4 w-4" /> Add charges</Button>
          <Button size="sm" onClick={() => setMode("checkout")}>Checkout</Button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto max-w-2xl">
          {/* Guest + stay summary */}
          <div className="mb-4 grid grid-cols-2 gap-2 rounded-lg border bg-muted/30 p-4 text-sm sm:grid-cols-3">
            <Info label="Folio" value={bill.folio_number} mono />
            <Info
              label={bill.rooms.length > 1 ? "Rooms" : "Room"}
              value={
                bill.rooms.length > 0
                  ? bill.rooms.map((r) => r.number).join(", ")
                  : `${bill.room?.number ?? "—"} (${bill.room?.type ?? "—"})`
              }
            />
            <Info label="Nights" value={String(bill.nights)} />
            <Info label="CNIC" value={bill.guest.cnic} />
            <Info label="Phone" value={bill.guest.phone} />
            {bill.guest.email && <Info label="Email" value={bill.guest.email} />}
            <Info label="Check-in" value={fmtDate(bill.check_in)} />
            {bill.check_out && <Info label="Check-out" value={fmtDate(bill.check_out)} />}
            {bill.guest.address && (
              <div className="col-span-2 sm:col-span-3">
                <div className="text-[11px] text-muted-foreground">Address</div>
                <div className="text-sm">{bill.guest.address}</div>
              </div>
            )}
          </div>

          {/* Charges grouped by day */}
          {bill.days.map((day) => (
            <div key={day.date} className="mb-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{day.date}</div>
              <div className="rounded-lg border">
                {day.charges.map((ch) => (
                  <div key={ch.charge_id} className="border-b p-3 last:border-0">
                    <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                      <span className="capitalize">
                        {ch.kind}{ch.room_number ? ` · Room ${ch.room_number}` : ""} · {ch.invoice_number}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono">Rs {rs(ch.total)}</span>
                        {isOpen && ch.can_remove && (
                          <button
                            type="button"
                            onClick={() => voidCharge(ch.charge_id)}
                            className="rounded border border-destructive/40 px-1.5 py-0.5 text-[10px] font-medium text-destructive hover:bg-destructive/10"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </div>
                    {ch.items.map((it) => (
                      <div key={it.id} className="flex items-center justify-between gap-2 text-sm">
                        <span className="min-w-0 flex-1">{it.quantity} × {it.name}{it.note ? ` (${it.note})` : ""}</span>
                        <span className="font-mono">Rs {rs(it.line_total)}</span>
                        {isOpen && ch.can_remove && (
                          <button
                            type="button"
                            onClick={() => voidItem(ch.charge_id, it.id, it.name)}
                            aria-label={`Remove ${it.name}`}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Totals */}
          <div className="mt-4 rounded-lg border bg-background p-4 text-sm">
            <Row label="Subtotal" value={rs(bill.subtotal)} />
            <Row label="Tax" value={rs(bill.tax_total)} />
            <div className="mt-1 flex justify-between border-t pt-2 text-base font-bold">
              <span>Grand total</span><span className="font-mono">Rs {rs(bill.grand_total)}</span>
            </div>
            {Number(bill.paid_total) > 0 && <Row label="Paid" value={rs(bill.paid_total)} />}
          </div>

          {/* Checkout panel */}
          {mode === "checkout" && (
            <div className="mt-4 rounded-lg border border-primary/40 bg-primary/5 p-4">
              <div className="mb-2 text-sm font-semibold">Settle &amp; check out</div>
              <div className="mb-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
                {PAYMENT_METHODS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setPayMethod(m)}
                    className={`rounded-md border px-2 py-2 text-xs font-medium capitalize ${payMethod === m ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                  >
                    {m.replace("_", " ")}
                  </button>
                ))}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Collect <b className="font-mono">Rs {rs(bill.grand_total)}</b> ({payMethod})</span>
                <Button onClick={doCheckout} disabled={busy}>{busy ? "Processing…" : "Confirm checkout & print bill"}</Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={mono ? "font-mono text-sm" : "text-sm"}>{value}</div>
    </div>
  );
}
function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">Rs {value}</span>
    </div>
  );
}
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
