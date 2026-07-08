import { BedDouble, Printer, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useFolio, useFolios } from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";
import { money } from "@/lib/utils";

import type { FolioBill, FolioRow, Tenant } from "@pos/shared/types";

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

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="flex h-full w-full max-w-lg flex-col bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">{bill?.guest.name ?? "Loading…"}</h2>
            <p className="text-xs text-muted-foreground">Consolidated stay bill</p>
          </div>
          <div className="flex items-center gap-2">
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
