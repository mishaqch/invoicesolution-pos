/** Check a guest in — opens a folio + auto-charges the room nights. */
import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";
import { rs } from "@/lib/money";

import { listRooms, openStay, type Room } from "@/features/hotel/api";

function errMsg(e: unknown): string {
  const anyE = e as { data?: Record<string, unknown>; status?: number };
  if (anyE?.data) {
    const d = anyE.data;
    if (typeof d.detail === "string") return d.detail;
    for (const v of Object.values(d)) {
      if (Array.isArray(v) && typeof v[0] === "string") return v[0];
      if (typeof v === "string") return v;
    }
  }
  return "Could not open the stay. Check your connection and try again.";
}

/** Local datetime string (YYYY-MM-DDTHH:mm) for the input default = now. */
function localNow(plusDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + plusDays);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function nightsBetween(checkIn: string, checkOut: string): number {
  if (!checkIn || !checkOut) return 1;
  const a = new Date(checkIn), b = new Date(checkOut);
  const days = Math.floor((Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) -
    Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) / 86400000);
  return Math.max(1, days);
}

export function OpenStayForm({
  onCancel,
  onOpened,
}: {
  onCancel: () => void;
  onOpened: (folioId: string) => void;
}) {
  const toast = useToast();
  const [rooms, setRooms] = useState<Room[]>([]);
  const [form, setForm] = useState({
    guest_name: "",
    guest_cnic: "",
    guest_phone: "",
    guest_email: "",
    guest_address: "",
    // Accompanying partner (e.g. a couple) — both optional.
    partner_name: "",
    partner_cnic: "",
    check_in: localNow(),
    expected_check_out: localNow(1),
  });
  const [roomIds, setRoomIds] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void listRooms({ status: "available" })
      .then(setRooms)
      .catch(() => toast.show({ message: "Could not load rooms.", variant: "destructive" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));
  function toggleRoom(id: string) {
    setRoomIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }
  const selectedRooms = rooms.filter((r) => roomIds.includes(r.id));
  const nights = useMemo(
    () => nightsBetween(form.check_in, form.expected_check_out),
    [form.check_in, form.expected_check_out],
  );
  const roomsTotal = selectedRooms.reduce((acc, r) => acc + Number(r.nightly_total) * nights, 0);

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!form.guest_name.trim()) e.guest_name = "Required";
    if (!form.guest_cnic.trim()) e.guest_cnic = "Required";
    if (!form.guest_phone.trim()) e.guest_phone = "Required";
    if (roomIds.length === 0) e.room = "Pick at least one room";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function submit() {
    if (!validate()) return;
    setSaving(true);
    try {
      const bill = await openStay({
        rooms: roomIds,
        guest_name: form.guest_name.trim(),
        guest_cnic: form.guest_cnic.trim(),
        guest_phone: form.guest_phone.trim(),
        guest_email: form.guest_email.trim() || undefined,
        guest_address: form.guest_address.trim() || undefined,
        partner_name: form.partner_name.trim() || undefined,
        partner_cnic: form.partner_cnic.trim() || undefined,
        check_in: new Date(form.check_in).toISOString(),
        expected_check_out: new Date(form.expected_check_out).toISOString(),
      });
      // The consolidated-bill payload includes the new folio id → go to detail.
      onOpened(bill.id);
    } catch (e) {
      toast.show({ message: errMsg(e), variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
        <button type="button" onClick={onCancel} className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <div className="text-sm font-semibold">Open new stay</div>
      </header>

      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto grid max-w-2xl gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Guest name *" error={errors.guest_name}>
              <input className={inp(errors.guest_name)} value={form.guest_name} onChange={(e) => set("guest_name", e.target.value)} placeholder="e.g. Ahmed Khan" />
            </Field>
            <Field label="CNIC *" error={errors.guest_cnic}>
              <input className={inp(errors.guest_cnic)} value={form.guest_cnic} onChange={(e) => set("guest_cnic", e.target.value)} placeholder="35201-1234567-1" inputMode="numeric" />
            </Field>
            <Field label="Phone *" error={errors.guest_phone}>
              <input className={inp(errors.guest_phone)} value={form.guest_phone} onChange={(e) => set("guest_phone", e.target.value)} placeholder="03xx xxxxxxx" inputMode="tel" />
            </Field>
            <Field label="Email (optional)">
              <input className={inp()} value={form.guest_email} onChange={(e) => set("guest_email", e.target.value)} placeholder="guest@email.com" inputMode="email" />
            </Field>
          </div>
          <Field label="Address (optional)">
            <input className={inp()} value={form.guest_address} onChange={(e) => set("guest_address", e.target.value)} placeholder="City / address" />
          </Field>

          {/* Accompanying partner (e.g. a couple). Optional — record a second
              person's name + CNIC when they share the stay. Not billed
              separately; the folio stays one guest bill. */}
          <div className="rounded-lg border border-dashed border-input p-3">
            <div className="mb-2 text-xs font-semibold text-muted-foreground">
              Accompanying partner <span className="font-normal">(optional — e.g. spouse)</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Partner full name">
                <input className={inp()} value={form.partner_name} onChange={(e) => set("partner_name", e.target.value)} placeholder="e.g. Fatima Khan" />
              </Field>
              <Field label="Partner CNIC">
                <input className={inp()} value={form.partner_cnic} onChange={(e) => set("partner_cnic", e.target.value)} placeholder="35201-1234567-2" inputMode="numeric" />
              </Field>
            </div>
          </div>

          <Field label={`Rooms * ${roomIds.length ? `(${roomIds.length} selected)` : ""}`} error={errors.room}>
            <div className={`max-h-56 overflow-auto rounded-md border p-1 ${errors.room ? "border-destructive" : "border-input"}`}>
              {rooms.length === 0 ? (
                <div className="p-3 text-sm text-muted-foreground">No available rooms.</div>
              ) : (
                rooms.map((r) => {
                  const on = roomIds.includes(r.id);
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => toggleRoom(r.id)}
                      className={`flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm ${on ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                    >
                      <span>{on ? "✓ " : ""}{r.room_number} · {r.room_type}</span>
                      <span className="font-mono text-xs">Rs {rs(r.nightly_total)}/night</span>
                    </button>
                  );
                })
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">One guest can book multiple rooms — tap to select several.</p>
          </Field>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Check-in">
              <input type="datetime-local" className={inp()} value={form.check_in} onChange={(e) => set("check_in", e.target.value)} />
            </Field>
            <Field label="Expected check-out">
              <input type="datetime-local" className={inp()} value={form.expected_check_out} onChange={(e) => set("expected_check_out", e.target.value)} />
            </Field>
          </div>

          {selectedRooms.length > 0 && (
            <div className="rounded-lg border bg-muted/40 p-4 text-sm">
              <div className="mb-1 flex justify-between"><span>Nights</span><span>{nights}</span></div>
              {selectedRooms.map((r) => (
                <div key={r.id} className="flex justify-between">
                  <span>{r.room_number} ({r.room_type}) × {nights}</span>
                  <span className="font-mono">Rs {rs(Number(r.nightly_total) * nights)}</span>
                </div>
              ))}
              <div className="mt-2 flex justify-between border-t pt-2 font-semibold">
                <span>Room charges on open</span><span className="font-mono">Rs {rs(roomsTotal)}</span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Food &amp; other charges are added during the stay; everything settles in one bill at checkout.</p>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
            <Button onClick={submit} disabled={saving}>{saving ? "Opening…" : `Open stay & charge ${roomIds.length > 1 ? `${roomIds.length} rooms` : "room"}`}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {error && <span className="mt-0.5 block text-xs text-destructive">{error}</span>}
    </label>
  );
}

function inp(error?: string): string {
  return `h-11 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring ${error ? "border-destructive" : "border-input"}`;
}
