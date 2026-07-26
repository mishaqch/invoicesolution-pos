/** A folio's running tab — view charges, add today's charges, checkout. */
import { ArrowLeft, BedDouble, Pencil, Plus, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";
import { ProductGrid } from "@/features/sale/ProductGrid";
import { ApiError } from "@/lib/api";
import { Money, rs } from "@/lib/money";
import { useSessionStore } from "@/stores/session";

import {
  addCharge,
  addRoom,
  cancelStay,
  checkoutFolio,
  getFolio,
  listRooms,
  removeCharge,
  removeItem,
  removeRoom,
  updateStay,
  type ChargeLine,
  type FolioBill,
  type Room,
  type UpdateStayBody,
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
  const role = useSessionStore((s) => s.role);
  // Cancelling a stay / removing a room is manager/owner-only (matches the
  // server-side permission gate). Editing guest details is open to cashiers.
  const canCancel = role === "owner" || role === "manager";
  const [bill, setBill] = useState<FolioBill | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"view" | "add" | "checkout" | "edit">("view");
  // Edit-stay form + add-room state.
  const [editForm, setEditForm] = useState<UpdateStayBody>({});
  const [availRooms, setAvailRooms] = useState<Room[]>([]);
  const [addRoomId, setAddRoomId] = useState<string>("");

  // Local add-charge cart (kept separate from the main till's sale store).
  const [cart, setCart] = useState<CartLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [payMethod, setPayMethod] = useState<string>("cash");
  // Cash tendered by the guest (typed string, e.g. "5000"). Only meaningful
  // when payMethod === "cash"; drives the change-due calculation below.
  const [tendered, setTendered] = useState<string>("");
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
      // Cash tender/change to print on the bill (cash only, and only when
      // there's actual change to hand back).
      const printChange =
        isCash && changeMoney !== null && !cashShort && changeMoney.gt(Money.zero());
      // Print the consolidated bill (non-fiscal for resort tenants). The
      // checkout itself has already SUCCEEDED at this point — a print failure
      // must NOT lose the sale, but we DO surface it so the cashier knows the
      // slip didn't come out (and can reprint), instead of it failing silently.
      try {
        const pr = await window.api.printer.printFolio({
          business_name: tenant?.business_name ?? "Resort",
          ntn: tenant?.ntn ?? "",
          address: tenant?.address ?? undefined,
          contact: tenant?.phone ?? undefined,
          width: 48,
          is_fiscal: tenant?.fbr_connection_type !== "none",
          folio: {
            ...settled,
            payment_method: payMethod,
            ...(printChange && tenderedMoney
              ? {
                  tendered: tenderedMoney.toStorageString(),
                  change_given: changeMoney!.toStorageString(),
                }
              : {}),
          },
        });
        if (pr?.success) {
          toast.show({ message: "Checked out. Bill printed.", variant: "success" });
        } else {
          toast.show({
            message: `Checked out, but printing failed: ${pr?.reason ?? "unknown"}.${pr?.fallbackPath ? ` Saved to ${pr.fallbackPath}` : ""}`,
            variant: "destructive",
          });
        }
      } catch (pe) {
        toast.show({
          message: `Checked out, but printing errored: ${errMsg(pe)}`,
          variant: "destructive",
        });
      }
      onCheckedOut();
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  // Open the edit form pre-filled from the current bill.
  function startEdit() {
    if (!bill) return;
    setEditForm({
      guest_name: bill.guest.name,
      guest_cnic: bill.guest.cnic,
      guest_phone: bill.guest.phone,
      guest_email: bill.guest.email || "",
      guest_address: bill.guest.address || "",
      partner_name: bill.guest.partner_name || "",
      partner_cnic: bill.guest.partner_cnic || "",
      // datetime-local wants "YYYY-MM-DDTHH:mm".
      check_in: bill.check_in ? toLocalInput(bill.check_in) : undefined,
      expected_check_out: bill.expected_check_out ? toLocalInput(bill.expected_check_out) : undefined,
    });
    setMode("edit");
  }

  async function saveEdit() {
    if (!bill) return;
    setBusy(true);
    try {
      // Convert the datetime-local strings back to ISO for the API.
      const body: UpdateStayBody = { ...editForm };
      if (body.check_in) body.check_in = new Date(body.check_in).toISOString();
      if (body.expected_check_out)
        body.expected_check_out = new Date(body.expected_check_out).toISOString();
      const updated = await updateStay(bill.id, body);
      setBill(updated);
      setMode("view");
      toast.show({ message: "Stay updated.", variant: "success" });
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  // Load available rooms when the edit form opens (for the "add room" picker).
  useEffect(() => {
    if (mode !== "edit") return;
    void listRooms({ status: "available" })
      .then((r) => setAvailRooms(r))
      .catch(() => setAvailRooms([]));
  }, [mode]);

  async function doAddRoom() {
    if (!bill || !addRoomId) return;
    setBusy(true);
    try {
      const updated = await addRoom(bill.id, addRoomId);
      setBill(updated);
      setAddRoomId("");
      // Refresh the available list (the added room is now occupied).
      void listRooms({ status: "available" }).then((r) => setAvailRooms(r)).catch(() => {});
      toast.show({ message: "Room added to the stay.", variant: "success" });
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function doRemoveRoom(roomId: string, number: string) {
    if (!bill) return;
    if (!confirm(`Remove Room ${number} from this stay? Its charges will be voided and the room freed.`)) return;
    setBusy(true);
    try {
      const updated = await removeRoom(bill.id, roomId);
      setBill(updated);
      toast.show({ message: `Room ${number} removed.`, variant: "info" });
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setBusy(false);
    }
  }

  async function doCancelStay() {
    if (!bill) return;
    const reason = prompt(
      `Cancel the WHOLE stay for ${bill.guest.name}? This voids every charge and frees all rooms.\n\nOptional reason:`,
    );
    if (reason === null) return; // user hit Cancel on the prompt
    setBusy(true);
    try {
      const updated = await cancelStay(bill.id, reason || "");
      setBill(updated);
      setMode("view");
      toast.show({ message: "Stay cancelled. Rooms freed.", variant: "info" });
      // Bounce back to the stays list — this folio is no longer open.
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

  // Cash tendered/change math — paisa-safe via Money (never float). Only the
  // cash method collects a physical amount and returns change; other methods
  // are settled for the exact total, so tendered/change don't apply.
  const isCash = payMethod === "cash";
  const dueMoney = bill ? Money.fromStr(bill.grand_total) : Money.zero();
  let tenderedMoney: Money | null = null;
  if (isCash && tendered.trim() !== "") {
    try { tenderedMoney = Money.fromStr(tendered); } catch { tenderedMoney = null; }
  }
  const changeMoney = tenderedMoney ? tenderedMoney.sub(dueMoney) : null;
  // Short by cash: a valid tendered amount below the total. Blocks checkout.
  const cashShort = isCash && tenderedMoney !== null && tenderedMoney.lt(dueMoney);

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
          {isOpen && (
            <Button size="sm" variant="outline" onClick={startEdit}>
              <Pencil className="mr-1 h-4 w-4" /> Edit stay
            </Button>
          )}
          {isOpen && (
            <Button size="sm" variant="outline" onClick={() => setMode("add")}><Plus className="mr-1 h-4 w-4" /> Add charges</Button>
          )}
          {isOpen && canCancel && (
            <Button
              size="sm"
              variant="outline"
              onClick={doCancelStay}
              disabled={busy}
              className="border-destructive/40 text-destructive hover:bg-destructive/10"
            >
              <XCircle className="mr-1 h-4 w-4" /> Cancel stay
            </Button>
          )}
          {isOpen && <Button size="sm" onClick={() => setMode("checkout")}>Checkout</Button>}
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
            {bill.guest.partner_name && <Info label="Partner" value={bill.guest.partner_name} />}
            {bill.guest.partner_cnic && <Info label="Partner CNIC" value={bill.guest.partner_cnic} />}
            <Info label="Check-in" value={fmtDate(bill.check_in)} />
            {bill.check_out && <Info label="Check-out" value={fmtDate(bill.check_out)} />}
            {bill.guest.address && (
              <div className="col-span-2 sm:col-span-3">
                <div className="text-[11px] text-muted-foreground">Address</div>
                <div className="text-sm">{bill.guest.address}</div>
              </div>
            )}
          </div>

          {/* --- EDIT STAY panel --- */}
          {mode === "edit" && isOpen && (
            <div className="mb-4 rounded-lg border border-primary/40 bg-primary/5 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-semibold">Edit stay</div>
                <button type="button" onClick={() => setMode("view")} className="text-xs text-muted-foreground hover:text-foreground">Close</button>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Guest name">
                  <input className={inputCls} value={editForm.guest_name ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, guest_name: e.target.value }))} />
                </Field>
                <Field label="CNIC">
                  <input className={inputCls} value={editForm.guest_cnic ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, guest_cnic: e.target.value }))} />
                </Field>
                <Field label="Phone">
                  <input className={inputCls} value={editForm.guest_phone ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, guest_phone: e.target.value }))} />
                </Field>
                <Field label="Email">
                  <input className={inputCls} value={editForm.guest_email ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, guest_email: e.target.value }))} />
                </Field>
                <Field label="Address" full>
                  <input className={inputCls} value={editForm.guest_address ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, guest_address: e.target.value }))} />
                </Field>
                <Field label="Partner name (optional)">
                  <input className={inputCls} value={editForm.partner_name ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, partner_name: e.target.value }))} />
                </Field>
                <Field label="Partner CNIC (optional)">
                  <input className={inputCls} value={editForm.partner_cnic ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, partner_cnic: e.target.value }))} />
                </Field>
                <Field label="Check-in">
                  <input type="datetime-local" className={inputCls} value={editForm.check_in ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, check_in: e.target.value }))} />
                </Field>
                <Field label="Expected check-out">
                  <input type="datetime-local" className={inputCls} value={editForm.expected_check_out ?? ""} onChange={(e) => setEditForm((f) => ({ ...f, expected_check_out: e.target.value }))} />
                </Field>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">Changing dates re-prices each room's nights.</p>

              <div className="mt-3 flex justify-end">
                <Button size="sm" onClick={saveEdit} disabled={busy}>{busy ? "Saving…" : "Save changes"}</Button>
              </div>

              {/* Rooms on this stay — add / remove */}
              <div className="mt-4 border-t pt-3">
                <div className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <BedDouble className="h-3.5 w-3.5" /> Rooms on this stay
                </div>
                <div className="space-y-1">
                  {bill.rooms.map((r) => (
                    <div key={r.id} className="flex items-center justify-between rounded border px-2 py-1 text-sm">
                      <span>Room {r.number} <span className="text-muted-foreground">({r.type}) · {r.nights}n</span></span>
                      {canCancel && bill.rooms.length > 1 && (
                        <button
                          type="button"
                          onClick={() => doRemoveRoom(r.id, r.number)}
                          disabled={busy}
                          className="rounded border border-destructive/40 px-1.5 py-0.5 text-[10px] font-medium text-destructive hover:bg-destructive/10"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <select
                    value={addRoomId}
                    onChange={(e) => setAddRoomId(e.target.value)}
                    className="h-8 flex-1 rounded-md border border-input bg-background px-2 text-xs"
                  >
                    <option value="">Add a room…</option>
                    {availRooms.map((r) => (
                      <option key={r.id} value={r.id}>Room {r.room_number} ({r.room_type}) — Rs {rs(r.nightly_total)}/night</option>
                    ))}
                  </select>
                  <Button size="sm" variant="outline" onClick={doAddRoom} disabled={busy || !addRoomId}>
                    <Plus className="mr-1 h-4 w-4" /> Add
                  </Button>
                </div>
              </div>
            </div>
          )}

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
              <span>Grand total</span><span className="font-mono">Rs {Money.fromStr(bill.grand_total).displayWhole()}</span>
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
                    onClick={() => { setPayMethod(m); setTendered(""); }}
                    className={`rounded-md border px-2 py-2 text-xs font-medium capitalize ${payMethod === m ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                  >
                    {m.replace("_", " ")}
                  </button>
                ))}
              </div>

              {/* Cash-only: tendered amount + change due. Other methods settle
                  for the exact total, so no tender/change is shown. */}
              {isCash && (
                <div className="mb-3 rounded-md border bg-background p-3">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <label htmlFor="tendered" className="text-sm text-muted-foreground">Cash tendered</label>
                    <div className="flex items-center gap-1">
                      <span className="text-sm text-muted-foreground">Rs</span>
                      <input
                        id="tendered"
                        type="text"
                        inputMode="decimal"
                        autoFocus
                        value={tendered}
                        onChange={(e) => setTendered(e.target.value.replace(/[^\d.]/g, ""))}
                        placeholder={rs(bill.grand_total)}
                        className="h-9 w-36 rounded-md border border-input bg-background px-2 text-right font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      />
                    </div>
                  </div>
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={() => setTendered(Money.fromStr(bill.grand_total).display())}
                      className="rounded border px-2 py-1 text-xs hover:bg-muted"
                    >
                      Exact
                    </button>
                    {[500, 1000, 5000].map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setTendered(String(n))}
                        className="rounded border px-2 py-1 text-xs hover:bg-muted"
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                  {changeMoney !== null && !cashShort && changeMoney.ge(Money.zero()) && (
                    <div className="flex items-center justify-between border-t pt-2 text-sm">
                      <span className="font-medium">Change due</span>
                      <span className="font-mono text-base font-bold text-primary">Rs {rs(changeMoney.toStorageString())}</span>
                    </div>
                  )}
                  {cashShort && (
                    <div className="border-t pt-2 text-xs font-medium text-destructive">
                      Tendered is less than the total. Collect at least Rs {rs(bill.grand_total)}.
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="text-sm">Collect <b className="font-mono">Rs {rs(bill.grand_total)}</b> ({payMethod.replace("_", " ")})</span>
                <Button onClick={doCheckout} disabled={busy || cashShort}>{busy ? "Processing…" : "Confirm checkout & print bill"}</Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const inputCls =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <div className={full ? "sm:col-span-2" : ""}>
      <div className="mb-1 text-[11px] text-muted-foreground">{label}</div>
      {children}
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

/** ISO string → "YYYY-MM-DDTHH:mm" for a datetime-local input (local time). */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
