import { BedDouble, Pencil, Plus, Printer, Trash2, X, XCircle } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useAddStayRoom,
  useCancelStay,
  useFolio,
  useFolios,
  useRemoveStayRoom,
  useRooms,
  useUpdateStay,
  type UpdateStayBody,
} from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";
import { money } from "@/lib/utils";

import type { FolioBill, FolioRow, Room, Tenant } from "@pos/shared/types";

function rows<T>(d: { results: T[] } | T[] | undefined): T[] {
  if (!d) return [];
  return Array.isArray(d) ? d : d.results;
}

function fmt(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const STATUS_STYLES: Record<string, string> = {
  open: "bg-primary-soft text-primary-soft-foreground",
  closed: "bg-slate-200 text-slate-700",
  cancelled: "bg-red-100 text-red-700",
};

export default function StaysAdmin() {
  const [status, setStatus] = useState<"open" | "closed" | "">("open");
  const { data, isLoading } = useFolios(status ? { status } : {});
  const folioRows = rows<FolioRow>(data);
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Stays"
        subtitle="Guest folios — open a folio to see the full consolidated bill."
        actions={
          <div className="inline-flex rounded-md border p-0.5">
            {(["open", "closed", ""] as const).map((s) => (
              <button
                key={s || "all"}
                type="button"
                onClick={() => setStatus(s)}
                className={`rounded px-3 py-1 text-sm ${status === s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                {s === "" ? "All" : s[0].toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        }
      />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Folio</TableHead>
              <TableHead>Guest</TableHead>
              <TableHead className="hidden md:table-cell">Phone</TableHead>
              <TableHead>Room</TableHead>
              <TableHead className="hidden lg:table-cell">Check-in</TableHead>
              <TableHead className="text-right">Nights</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : folioRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                  <BedDouble className="mx-auto mb-2 h-6 w-6 opacity-50" />
                  No {status || ""} stays.
                </TableCell>
              </TableRow>
            ) : (
              folioRows.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="font-mono text-xs">{f.folio_number}</TableCell>
                  <TableCell className="font-medium">{f.guest_name}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{f.guest_phone}</TableCell>
                  <TableCell>{f.room_number ?? "—"}</TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{fmt(f.check_in)}</TableCell>
                  <TableCell className="text-right">{f.nights}</TableCell>
                  <TableCell><Badge className={STATUS_STYLES[f.status] ?? ""}>{f.status}</Badge></TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" onClick={() => setOpenId(f.id)}>View bill</Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {openId && <FolioBillDrawer folioId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

/** Escape a value for safe interpolation into the print HTML. */
function esc(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Open the consolidated stay bill in a new window and trigger the browser's
 * print dialog. A standalone document (not the SPA) keeps the app's layout
 * out of the printout and needs no global print CSS. A4-friendly.
 */
function printFolioBill(bill: FolioBill, tenant: Tenant | null): void {
  const roomsLabel =
    bill.rooms.length > 0
      ? bill.rooms.map((r) => `${r.number} (${r.type})`).join(", ")
      : bill.room
        ? `${bill.room.number} (${bill.room.type})`
        : "—";

  const dayRows = bill.days
    .map((day) => {
      const charges = day.charges
        .map((ch) => {
          const items = ch.items
            .map(
              (it) => `
              <tr>
                <td>${esc(it.quantity)} × ${esc(it.name)}${it.note ? ` <span class="muted">(${esc(it.note)})</span>` : ""}</td>
                <td class="num">${esc(money(it.line_total))}</td>
              </tr>`,
            )
            .join("");
          const head = `${esc(ch.kind)}${ch.room_number ? ` · Room ${esc(ch.room_number)}` : ""} · ${esc(ch.invoice_number)}`;
          return `
            <tr class="charge-head">
              <td>${head}</td>
              <td class="num">${esc(money(ch.total))}</td>
            </tr>
            ${items}`;
        })
        .join("");
      return `
        <tr class="day-head"><td colspan="2">${esc(day.date)}</td></tr>
        ${charges}`;
    })
    .join("");

  const line = (label: string, value: string, cls = "") =>
    `<div class="totrow ${cls}"><span>${esc(label)}</span><span class="num">Rs ${esc(value)}</span></div>`;

  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Bill ${esc(bill.folio_number)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #0f172a; margin: 0; padding: 24px; font-size: 13px; }
  .wrap { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0; }
  .sub { color: #64748b; font-size: 12px; margin-top: 2px; }
  .head { text-align: center; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 16px; }
  .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; margin-bottom: 16px; }
  .meta div { display: flex; justify-content: space-between; border-bottom: 1px dotted #cbd5e1; padding: 3px 0; }
  .meta .k { color: #64748b; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
  td { padding: 4px 6px; vertical-align: top; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .day-head td { background: #f1f5f9; font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: .04em; padding-top: 8px; }
  .charge-head td { border-top: 1px solid #e2e8f0; color: #475569; font-size: 12px; padding-top: 6px; }
  .muted { color: #94a3b8; }
  .totals { margin-left: auto; width: 280px; border-top: 2px solid #0f172a; padding-top: 8px; }
  .totrow { display: flex; justify-content: space-between; padding: 3px 0; }
  .totrow.grand { font-size: 15px; font-weight: 700; border-top: 1px solid #cbd5e1; margin-top: 4px; padding-top: 6px; }
  .foot { text-align: center; color: #64748b; font-size: 11px; margin-top: 28px; }
  @media print { body { padding: 0; } }
</style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <h1>${esc(tenant?.business_name ?? "Resort")}</h1>
      ${tenant?.address ? `<div class="sub">${esc(tenant.address)}</div>` : ""}
      ${tenant?.phone ? `<div class="sub">${esc(tenant.phone)}</div>` : ""}
      ${tenant?.ntn ? `<div class="sub">NTN: ${esc(tenant.ntn)}</div>` : ""}
      <div class="sub" style="margin-top:6px;font-weight:600;color:#0f172a;">Consolidated Stay Bill</div>
    </div>

    <div class="meta">
      <div><span class="k">Folio</span><span>${esc(bill.folio_number)}</span></div>
      <div><span class="k">Status</span><span>${esc(bill.status)}</span></div>
      <div><span class="k">Guest</span><span>${esc(bill.guest.name)}</span></div>
      <div><span class="k">Phone</span><span>${esc(bill.guest.phone)}</span></div>
      <div><span class="k">CNIC</span><span>${esc(bill.guest.cnic)}</span></div>
      <div><span class="k">${bill.rooms.length > 1 ? "Rooms" : "Room"}</span><span>${esc(roomsLabel)}</span></div>
      <div><span class="k">Nights</span><span>${esc(bill.nights)}</span></div>
      <div><span class="k">Check-in</span><span>${esc(fmt(bill.check_in))}</span></div>
      <div><span class="k">Check-out</span><span>${esc(fmt(bill.check_out))}</span></div>
      ${bill.guest.email ? `<div><span class="k">Email</span><span>${esc(bill.guest.email)}</span></div>` : ""}
    </div>

    <table>${dayRows}</table>

    <div class="totals">
      ${line("Subtotal", money(bill.subtotal))}
      ${line("Tax", money(bill.tax_total))}
      ${line("Grand total", money(bill.grand_total), "grand")}
      ${Number(bill.paid_total) > 0 ? line("Paid", money(bill.paid_total)) : ""}
      ${Number(bill.balance) !== 0 ? line("Balance", money(bill.balance)) : ""}
    </div>

    <div class="foot">Thank you for staying with us.</div>
  </div>
  <script>window.onload = function () { window.print(); };</script>
</body>
</html>`;

  const w = window.open("", "_blank", "width=800,height=900");
  if (!w) {
    alert("Please allow pop-ups for this site to print the bill.");
    return;
  }
  w.document.open();
  w.document.write(html);
  w.document.close();
}

function FolioBillDrawer({ folioId, onClose }: { folioId: string; onClose: () => void }) {
  const { data: bill, isLoading } = useFolio(folioId);
  const tenant = useAuthStore((s) => s.tenant);
  const role = useAuthStore((s) => s.role);
  // Cancel / remove-room are manager/owner-only (mirrors the server gate).
  const canCancel = role === "owner" || role === "manager";
  const isOpen = bill?.status === "open";

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<UpdateStayBody>({});
  const [addRoomId, setAddRoomId] = useState("");

  const updateStay = useUpdateStay();
  const addStayRoom = useAddStayRoom();
  const removeStayRoom = useRemoveStayRoom();
  const cancelStay = useCancelStay();
  const busy =
    updateStay.isPending || addStayRoom.isPending || removeStayRoom.isPending || cancelStay.isPending;

  // Available rooms for the "add room" picker (only fetched while editing).
  const { data: roomsData } = useRooms(editing ? { status: "available" } : {});
  const availRooms: Room[] = editing ? rows<Room>(roomsData) : [];

  function startEdit() {
    if (!bill) return;
    setForm({
      guest_name: bill.guest.name,
      guest_cnic: bill.guest.cnic,
      guest_phone: bill.guest.phone,
      guest_email: bill.guest.email || "",
      guest_address: bill.guest.address || "",
      check_in: bill.check_in ? toLocalInput(bill.check_in) : undefined,
      expected_check_out: bill.expected_check_out ? toLocalInput(bill.expected_check_out) : undefined,
    });
    setEditing(true);
  }

  async function saveEdit() {
    if (!bill) return;
    const body: UpdateStayBody = { ...form };
    if (body.check_in) body.check_in = new Date(body.check_in).toISOString();
    if (body.expected_check_out) body.expected_check_out = new Date(body.expected_check_out).toISOString();
    try {
      await updateStay.mutateAsync({ id: bill.id, ...body });
      setEditing(false);
    } catch (e) {
      alert(errText(e));
    }
  }

  async function doAddRoom() {
    if (!bill || !addRoomId) return;
    try {
      await addStayRoom.mutateAsync({ id: bill.id, room: addRoomId });
      setAddRoomId("");
    } catch (e) {
      alert(errText(e));
    }
  }

  async function doRemoveRoom(roomId: string, number: string) {
    if (!bill) return;
    if (!confirm(`Remove Room ${number}? Its charges are voided and the room is freed.`)) return;
    try {
      await removeStayRoom.mutateAsync({ id: bill.id, roomId });
    } catch (e) {
      alert(errText(e));
    }
  }

  async function doCancel() {
    if (!bill) return;
    const reason = prompt(
      `Cancel the WHOLE stay for ${bill.guest.name}? This voids every charge and frees all rooms.\n\nOptional reason:`,
    );
    if (reason === null) return;
    try {
      await cancelStay.mutateAsync({ id: bill.id, reason: reason || "" });
      onClose();
    } catch (e) {
      alert(errText(e));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="flex h-full w-full max-w-lg flex-col bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">{bill?.guest.name ?? "Loading…"}</h2>
            <p className="text-xs text-muted-foreground">Consolidated stay bill</p>
          </div>
          <div className="flex items-center gap-2">
            {isOpen && (
              <Button variant="outline" size="sm" onClick={editing ? () => setEditing(false) : startEdit}>
                <Pencil className="mr-1 h-4 w-4" /> {editing ? "Done" : "Edit"}
              </Button>
            )}
            {isOpen && canCancel && (
              <Button
                variant="outline"
                size="sm"
                onClick={doCancel}
                disabled={busy}
                className="border-destructive/40 text-destructive hover:bg-destructive/10"
              >
                <XCircle className="mr-1 h-4 w-4" /> Cancel stay
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={!bill}
              onClick={() => bill && printFolioBill(bill, tenant)}
            >
              <Printer className="mr-1 h-4 w-4" /> Print bill
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-5">
          {isLoading || !bill ? (
            <div className="p-6 text-center text-sm text-muted-foreground">Loading…</div>
          ) : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-2 rounded-lg border bg-muted/30 p-4 text-sm">
                <Info label="Folio" value={bill.folio_number} mono />
                <Info label="Status" value={bill.status} />
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
                <Info label="Check-in" value={fmt(bill.check_in)} />
                <Info label="Check-out" value={fmt(bill.check_out)} />
                {bill.guest.email && <Info label="Email" value={bill.guest.email} />}
                {bill.guest.address && (
                  <div className="col-span-2">
                    <div className="text-[11px] text-muted-foreground">Address</div>
                    <div className="text-sm">{bill.guest.address}</div>
                  </div>
                )}
              </div>

              {/* --- EDIT panel --- */}
              {editing && isOpen && (
                <div className="mb-4 rounded-lg border border-primary/40 bg-primary/5 p-4">
                  <div className="mb-3 text-sm font-semibold">Edit stay</div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <EditField label="Guest name" value={form.guest_name ?? ""} onChange={(v) => setForm((f) => ({ ...f, guest_name: v }))} />
                    <EditField label="CNIC" value={form.guest_cnic ?? ""} onChange={(v) => setForm((f) => ({ ...f, guest_cnic: v }))} />
                    <EditField label="Phone" value={form.guest_phone ?? ""} onChange={(v) => setForm((f) => ({ ...f, guest_phone: v }))} />
                    <EditField label="Email" value={form.guest_email ?? ""} onChange={(v) => setForm((f) => ({ ...f, guest_email: v }))} />
                    <div className="sm:col-span-2">
                      <EditField label="Address" value={form.guest_address ?? ""} onChange={(v) => setForm((f) => ({ ...f, guest_address: v }))} />
                    </div>
                    <EditField label="Check-in" type="datetime-local" value={form.check_in ?? ""} onChange={(v) => setForm((f) => ({ ...f, check_in: v }))} />
                    <EditField label="Expected check-out" type="datetime-local" value={form.expected_check_out ?? ""} onChange={(v) => setForm((f) => ({ ...f, expected_check_out: v }))} />
                  </div>
                  <p className="mt-2 text-[11px] text-muted-foreground">Changing dates re-prices each room's nights.</p>
                  <div className="mt-3 flex justify-end">
                    <Button size="sm" onClick={saveEdit} disabled={busy}>{updateStay.isPending ? "Saving…" : "Save changes"}</Button>
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
                              className="inline-flex items-center gap-1 rounded border border-destructive/40 px-1.5 py-0.5 text-[10px] font-medium text-destructive hover:bg-destructive/10"
                            >
                              <Trash2 className="h-3 w-3" /> Remove
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
                          <option key={r.id} value={r.id}>Room {r.room_number} ({r.room_type}) — Rs {money(r.nightly_total)}/night</option>
                        ))}
                      </select>
                      <Button size="sm" variant="outline" onClick={doAddRoom} disabled={busy || !addRoomId}>
                        <Plus className="mr-1 h-4 w-4" /> Add
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {bill.days.map((day) => (
                <div key={day.date} className="mb-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{day.date}</div>
                  <div className="rounded-lg border">
                    {day.charges.map((ch, ci) => (
                      <div key={ci} className="border-b p-3 last:border-0">
                        <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                          <span className="capitalize">
                            {ch.kind}{ch.room_number ? ` · Room ${ch.room_number}` : ""} · {ch.invoice_number}
                          </span>
                          <span className="font-mono">Rs {money(ch.total)}</span>
                        </div>
                        {ch.items.map((it, ii) => (
                          <div key={ii} className="flex justify-between text-sm">
                            <span>{it.quantity} × {it.name}{it.note ? ` (${it.note})` : ""}</span>
                            <span className="font-mono">Rs {money(it.line_total)}</span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <div className="mt-4 rounded-lg border bg-background p-4 text-sm">
                <Row label="Subtotal" value={money(bill.subtotal)} />
                <Row label="Tax" value={money(bill.tax_total)} />
                <div className="mt-1 flex justify-between border-t pt-2 text-base font-bold">
                  <span>Grand total</span><span className="font-mono">Rs {money(bill.grand_total)}</span>
                </div>
                {Number(bill.paid_total) > 0 && <Row label="Paid" value={money(bill.paid_total)} />}
                {Number(bill.balance) !== 0 && <Row label="Balance" value={money(bill.balance)} />}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function EditField({
  label, value, onChange, type = "text",
}: {
  label: string; value: string; onChange: (v: string) => void; type?: string;
}) {
  return (
    <div>
      <div className="mb-1 text-[11px] text-muted-foreground">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
    </div>
  );
}

/** ISO string → "YYYY-MM-DDTHH:mm" for a datetime-local input (local time). */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Pull a human message out of an API error (best effort). */
function errText(e: unknown): string {
  if (e && typeof e === "object") {
    const data = (e as { data?: unknown }).data;
    if (data && typeof data === "object") {
      const d = data as Record<string, unknown>;
      if (typeof d.detail === "string") return d.detail;
      for (const v of Object.values(d)) {
        if (Array.isArray(v) && typeof v[0] === "string") return v[0];
        if (typeof v === "string") return v;
      }
    }
    if (typeof (e as { message?: unknown }).message === "string") return (e as { message: string }).message;
  }
  return "Something went wrong. Please try again.";
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={mono ? "font-mono text-sm" : "text-sm capitalize"}>{value}</div>
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
