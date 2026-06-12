/**
 * Tenant > Invoices.
 *
 * FBR-compliance is the hot path of the product, so this screen leads
 * with the lifecycle KPIs (validated / submitted / failed / etc.) and
 * the search box gets equal weight with status filtering.
 *
 * KPI tiles are clickable status-filters: clicking "Failed" sets the
 * status query param to "failed" and flashes the table to that subset.
 * Tile counts come from /sales/invoices/summary/, which honours the
 * branch + date filter so the numbers match the table.
 */

import {
  AlertOctagon,
  CheckCircle2,
  CircleDashed,
  Clock,
  FilePenLine,
  Plus,
  Receipt,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
// Named import (not default) — react-qr-code v2 ships CJS with both
// `exports.default` and `exports.QRCode`. Under Vite's ESM interop the
// default import sometimes resolves to the module namespace object
// instead of the component, producing "Element type is invalid".
import { QRCode } from "react-qr-code";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  invoiceStatusHint,
  invoiceStatusLabel,
  invoiceStatusVariant,
} from "@/features/invoices/status";
import { useBranches, useInvoices, useInvoiceSummary } from "@/lib/queries";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Status taxonomy
//
// Backend status values (from apps/sales/models.py INVOICE_STATUSES):
//   pending_sync, submitted, valid, failed, edited, partially_edited,
//   cancelled, partially_cancelled, partially_edited_and_cancelled, finalized.
//
// We bucket them into 6 KPI tiles a tenant cares about. The bucket is
// also what the dropdown filter sends to the API as a single status
// value (the API accepts only exact matches today).
// ---------------------------------------------------------------------------

const STATUS_FILTER_OPTIONS = [
  { value: "", label: "All statuses" },
  // "Validated" sums valid + finalized (a finalized invoice is a validated one
  // that aged past 72h). The API accepts the comma list and filters on both, so
  // the rows match the "Validated by FBR" KPI tile count.
  { value: "valid,finalized", label: "Validated" },
  { value: "finalized", label: "Finalized (>72h)" },
  { value: "submitted", label: "Submitted" },
  { value: "failed", label: "Failed" },
  { value: "pending_sync", label: "Draft (not yet submitted)" },
  { value: "edited", label: "Edited" },
  { value: "partially_edited", label: "Partially edited" },
  { value: "cancelled", label: "Cancelled" },
  { value: "partially_cancelled", label: "Partially cancelled" },
] as const;

interface KpiTile {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Status values that count toward this tile. */
  statuses: string[];
  /** When the user clicks this tile, this is the value sent to the
   *  status filter. Most tiles map 1-1 to a real status; "Validated"
   *  sums valid+finalized (only "valid" is sent). */
  filterValue: string;
  tone: "neutral" | "success" | "info" | "warning" | "danger" | "muted";
}

const TILES: KpiTile[] = [
  {
    key: "total",
    label: "All invoices",
    icon: Receipt,
    statuses: [],          // sentinel: total count
    filterValue: "",
    tone: "neutral",
  },
  {
    key: "validated",
    label: "Validated by FBR",
    icon: CheckCircle2,
    statuses: ["valid", "finalized"],
    filterValue: "valid,finalized",
    tone: "success",
  },
  {
    key: "submitted",
    label: "Submitted",
    icon: Clock,
    statuses: ["submitted"],
    filterValue: "submitted",
    tone: "info",
  },
  {
    key: "failed",
    label: "Failed",
    icon: AlertOctagon,
    statuses: ["failed"],
    filterValue: "failed",
    tone: "danger",
  },
  {
    key: "pending",
    label: "Drafts (not submitted)",
    icon: CircleDashed,
    statuses: ["pending_sync"],
    filterValue: "pending_sync",
    tone: "warning",
  },
  {
    key: "edited_cancelled",
    label: "Edited / cancelled",
    icon: FilePenLine,
    statuses: [
      "edited",
      "partially_edited",
      "cancelled",
      "partially_cancelled",
      "partially_edited_and_cancelled",
    ],
    filterValue: "cancelled",
    tone: "muted",
  },
];

const TONE_STYLES: Record<KpiTile["tone"], string> = {
  neutral: "border-border bg-card",
  success: "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/30",
  info: "border-sky-200 bg-sky-50/60 dark:border-sky-900/60 dark:bg-sky-950/30",
  warning: "border-amber-200 bg-amber-50/60 dark:border-amber-900/60 dark:bg-amber-950/30",
  danger: "border-rose-200 bg-rose-50/60 dark:border-rose-900/60 dark:bg-rose-950/30",
  muted: "border-border bg-muted/40",
};

const TONE_ICON: Record<KpiTile["tone"], string> = {
  neutral: "text-muted-foreground",
  success: "text-emerald-600 dark:text-emerald-400",
  info: "text-sky-600 dark:text-sky-400",
  warning: "text-amber-600 dark:text-amber-400",
  danger: "text-rose-600 dark:text-rose-400",
  muted: "text-muted-foreground",
};

// Badge variant + label + hover-hint live in
// features/invoices/status.ts (single source of truth across every
// invoice surface). Keep the column rendering thin.

// ---------------------------------------------------------------------------

/**
 * Render the unique tail of a PRAL-issued FBR invoice number.
 *
 * PRAL formats the number as `<seller-NTN(13)><unique-tail(14)>` — so
 * every invoice for the same tenant starts with the same 13-character
 * NTN prefix. Showing the prefix in a per-row list cell wastes space
 * and (confusingly) makes every invoice look identical at a glance.
 *
 * Returns the last 14 chars when the input looks like the standard
 * 27-char PRAL format, otherwise returns the whole string unchanged
 * (defensive — keeps the renderer safe if PRAL ever issues a
 * different shape).
 */
function fbrInvoiceTail(fbrNumber: string | null | undefined): string {
  if (!fbrNumber) return "";
  if (fbrNumber.length === 27) return fbrNumber.slice(13);
  return fbrNumber;
}

export default function InvoicesList() {
  const [status, setStatus] = useState("");
  const [branch, setBranch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [activeTile, setActiveTile] = useState<string>("total");

  const branches = useBranches();
  const filters = { status, branch, from, to, q };
  const { data, isLoading } = useInvoices(filters);
  const summary = useInvoiceSummary({ branch, from, to });

  const tileCounts = useMemo(() => {
    const out: Record<string, number> = {};
    if (!summary.data) return out;
    for (const tile of TILES) {
      if (tile.key === "total") {
        out[tile.key] = summary.data.total_count;
        continue;
      }
      out[tile.key] = tile.statuses.reduce(
        (acc, s) => acc + (summary.data!.by_status[s]?.count ?? 0),
        0,
      );
    }
    return out;
  }, [summary.data]);

  function applyTile(tile: KpiTile) {
    setActiveTile(tile.key);
    setStatus(tile.filterValue);
  }

  function clearFilters() {
    setStatus("");
    setBranch("");
    setFrom("");
    setTo("");
    setQ("");
    setActiveTile("total");
  }

  const activeFilterCount =
    (status ? 1 : 0) + (branch ? 1 : 0) + (from ? 1 : 0) + (to ? 1 : 0) + (q ? 1 : 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Invoices"
        subtitle="FBR Digital Invoicing — track every invoice across its lifecycle."
        actions={
          <Button asChild>
            <Link to="/sales/new">
              <Plus className="mr-1 h-4 w-4" /> New invoice
            </Link>
          </Button>
        }
      />

      {/* KPI tiles ------------------------------------------------------- */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {TILES.map((tile) => {
          const Icon = tile.icon;
          const count = tileCounts[tile.key] ?? 0;
          const isActive = activeTile === tile.key;
          return (
            <button
              key={tile.key}
              type="button"
              onClick={() => applyTile(tile)}
              aria-pressed={isActive}
              className={cn(
                "rounded-lg border p-4 text-left shadow-sm transition-all",
                "hover:shadow-md hover:-translate-y-0.5",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
                TONE_STYLES[tile.tone],
                isActive && "ring-2 ring-primary ring-offset-1",
              )}
            >
              <div className="flex items-start justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  {tile.label}
                </span>
                <Icon className={cn("h-4 w-4 shrink-0", TONE_ICON[tile.tone])} />
              </div>
              <div className="mt-2 text-2xl font-semibold tabular-nums">
                {summary.isLoading ? "…" : count.toLocaleString()}
              </div>
            </button>
          );
        })}
      </div>

      {/* Filter row ----------------------------------------------------- */}
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
            <div className="space-y-1.5 md:col-span-4">
              <Label htmlFor="invoice-search">Search</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="invoice-search"
                  className="pl-8 pr-8"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Invoice #, FBR #, or buyer name"
                />
                {q && (
                  <button
                    type="button"
                    onClick={() => setQ("")}
                    aria-label="Clear search"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="invoice-status">Status</Label>
              <Select
                id="invoice-status"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  // Sync the tile selection when the dropdown drives status.
                  const matching = TILES.find((t) => t.filterValue === e.target.value);
                  setActiveTile(matching ? matching.key : "total");
                }}
              >
                {STATUS_FILTER_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </Select>
            </div>

            {/* Branch filter — only shown when the tenant actually has
                branches. Single-branch / branchless tenants don't need
                a dropdown that filters across one (or zero) options. */}
            {(branches.data?.results.length ?? 0) > 0 && (
              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="invoice-branch">Branch</Label>
                <Select
                  id="invoice-branch"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                >
                  <option value="">All branches</option>
                  {branches.data!.results.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </Select>
              </div>
            )}

            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="invoice-from">From</Label>
              <Input
                id="invoice-from"
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>

            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="invoice-to">To</Label>
              <Input
                id="invoice-to"
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </div>

          {activeFilterCount > 0 && (
            <div className="flex items-center justify-between border-t pt-3">
              <p className="text-xs text-muted-foreground">
                {activeFilterCount} filter{activeFilterCount === 1 ? "" : "s"} active
                {data && ` · ${data.count.toLocaleString()} invoice${data.count === 1 ? "" : "s"}`}
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={clearFilters}
                className="h-7 px-2 text-xs"
              >
                <X className="mr-1 h-3.5 w-3.5" /> Clear all
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Table ---------------------------------------------------------- */}
      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice #</TableHead>
              <TableHead className="hidden lg:table-cell">FBR #</TableHead>
              <TableHead className="hidden md:table-cell">Date</TableHead>
              <TableHead className="hidden md:table-cell">Buyer</TableHead>
              <TableHead className="hidden text-right sm:table-cell">Items</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  Loading invoices…
                </TableCell>
              </TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  {activeFilterCount > 0
                    ? "No invoices match the current filters."
                    : "No invoices yet. Create your first one with the New invoice button."}
                </TableCell>
              </TableRow>
            ) : (
              data?.results.map((i) => (
                <TableRow key={i.id} className="hover:bg-muted/30">
                  <TableCell className="font-mono text-xs">
                    <Link to={`/sales/${i.id}`} className="font-medium text-primary hover:underline">
                      {i.local_invoice_number}
                    </Link>
                    {/* Buyer + date surfaced under the invoice # on small
                        screens where their columns are hidden. */}
                    <span className="block text-[11px] font-sans text-muted-foreground md:hidden">
                      {i.buyer_name ?? "Walk-in"} · {i.invoice_date}
                    </span>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs lg:table-cell">
                    {i.fbr_invoice_number ? (
                      // Tiny QR + the UNIQUE TAIL of the FBR number so
                      // the row stays compact. PRAL's invoice number
                      // is <seller-NTN (13 chars)><unique-tail (14 chars)>;
                      // every row in this tenant's list has the same
                      // NTN prefix, so showing the prefix wastes space
                      // and looks (confusingly) like every invoice has
                      // the same FBR number. Show the unique tail
                      // instead, with the full string in the tooltip.
                      // Full number lives on the detail page.
                      // QR encodes EXACTLY the bare FBR invoice number —
                      // that's what Tax Asaan verifies; a JSON blob reads
                      // as "invalid". Mirrors the detail page + PDF.
                      <div
                        className="flex items-center gap-2"
                        title={i.fbr_invoice_number ?? undefined}
                      >
                        <div className="rounded-sm bg-white p-0.5">
                          <QRCode
                            value={i.fbr_invoice_number}
                            size={28}
                            level="L"
                            aria-label="FBR receipt QR"
                          />
                        </div>
                        <span className="font-mono text-[11px]">
                          {fbrInvoiceTail(i.fbr_invoice_number)}
                        </span>
                      </div>
                    ) : i.fbr_invoice_number ? (
                      <span
                        className="font-mono text-[11px]"
                        title={i.fbr_invoice_number}
                      >
                        {fbrInvoiceTail(i.fbr_invoice_number)}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground tabular-nums md:table-cell">
                    {i.invoice_date}
                  </TableCell>
                  <TableCell className="hidden max-w-[180px] truncate text-sm md:table-cell">
                    {i.buyer_name ?? <span className="text-muted-foreground">Walk-in</span>}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums text-sm sm:table-cell">
                    {i.items.length}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    Rs {Number(i.grand_total).toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={invoiceStatusVariant(i.status)}
                      title={invoiceStatusHint(i.status)}
                    >
                      {invoiceStatusLabel(i.status)}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {data && data.count > 0 && (
        <p className="text-xs text-muted-foreground">
          Showing {data.results.length} of {data.count.toLocaleString()} invoices.
        </p>
      )}
    </div>
  );
}
