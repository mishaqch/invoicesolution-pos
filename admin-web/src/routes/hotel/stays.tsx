import { BedDouble, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useFolio, useFolios } from "@/lib/queries";
import { money } from "@/lib/utils";

import type { FolioRow } from "@pos/shared/types";

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

function FolioBillDrawer({ folioId, onClose }: { folioId: string; onClose: () => void }) {
  const { data: bill, isLoading } = useFolio(folioId);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="flex h-full w-full max-w-lg flex-col bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">{bill?.guest.name ?? "Loading…"}</h2>
            <p className="text-xs text-muted-foreground">Consolidated stay bill</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></Button>
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
              </div>

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
