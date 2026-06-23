/**
 * Stock card drawer — the full history of ONE product at ONE location.
 *
 * Answers the two questions the Stock list alone can't: "what did I open
 * with?" and "where did my stock go?". Shows opening / in / out / current as
 * headline numbers, then the running-balance ledger (newest first) so every
 * change — a sale, a return from a cancelled invoice, a manual correction —
 * is accounted for.
 *
 * Plain fixed-overlay modal (the app has no Dialog/Sheet primitive yet; this
 * mirrors the Cancel-sale modal pattern in invoice-detail).
 */
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useStockCard } from "@/lib/queries";
import { qty } from "@/lib/utils";

/** Human-friendly label for a raw movement_type. */
const MOVEMENT_LABELS: Record<string, string> = {
  opening_balance: "Opening balance",
  sale: "Sold (invoice)",
  return: "Returned to stock",
  purchase: "Purchase received",
  transfer_in: "Transfer in",
  transfer_out: "Transfer out",
  adjustment_in: "Stock in (adjust)",
  adjustment_out: "Stock out (adjust)",
  damage: "Damage write-off",
  expiry: "Expiry write-off",
};

function label(t: string): string {
  return MOVEMENT_LABELS[t] ?? t;
}

export function StockCardDrawer({
  productId,
  productName,
  warehouse,
  branch,
  onClose,
}: {
  productId: string;
  productName: string;
  /** Pass exactly one: warehouse (DI) or branch (POS). */
  warehouse?: string;
  branch?: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useStockCard({ product: productId, warehouse, branch });

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full max-w-2xl flex-col bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">{productName}</h2>
            <p className="text-xs text-muted-foreground">Stock card — opening, movements & on-hand</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Surface a load failure explicitly — otherwise a failed fetch just
            shows dashes + "no movements", which reads as "empty" when it's
            really an error. */}
        {isError && (
          <div className="border-b bg-destructive/10 px-5 py-3 text-sm text-destructive">
            Couldn’t load this stock card. {error instanceof Error ? error.message : ""} Please retry.
          </div>
        )}

        {/* Headline numbers */}
        <div className="grid grid-cols-2 gap-px border-b bg-border sm:grid-cols-4">
          <Stat label="Opening" value={data ? qty(data.opening) : undefined} sub={data?.opening_at ? new Date(data.opening_at).toLocaleDateString() : "—"} />
          <Stat label="Total in" value={data ? qty(data.total_in) : undefined} tone="positive" />
          <Stat label="Total out" value={data ? qty(data.total_out) : undefined} tone="negative" />
          <Stat label="On hand now" value={data ? qty(data.current) : undefined} strong />
        </div>

        {/* Running ledger */}
        <div className="min-h-0 flex-1 overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 bg-background">
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Change</TableHead>
                <TableHead className="text-right">Balance</TableHead>
                <TableHead className="hidden md:table-cell">Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
              ) : (data?.ledger.length ?? 0) === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">No movements yet for this product here.</TableCell></TableRow>
              ) : (
                data!.ledger.map((row) => {
                  const change = Number(row.quantity);
                  return (
                    <TableRow key={row.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {new Date(row.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-xs">
                        {label(row.movement_type)}
                        {row.performed_by && (
                          <span className="block text-[11px] text-muted-foreground">by {row.performed_by}</span>
                        )}
                      </TableCell>
                      <TableCell className={`text-right font-mono text-sm ${change < 0 ? "text-destructive" : change > 0 ? "text-emerald-600" : ""}`}>
                        {change > 0 ? `+${qty(row.quantity)}` : qty(row.quantity)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">{qty(row.balance_after)}</TableCell>
                      <TableCell className="hidden max-w-[16rem] truncate text-xs text-muted-foreground md:table-cell" title={row.reason}>
                        {row.reason || "—"}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
  strong,
}: {
  label: string;
  value: string | undefined;
  sub?: string;
  tone?: "positive" | "negative";
  strong?: boolean;
}) {
  return (
    <div className="bg-background px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={`font-mono ${strong ? "text-xl font-semibold" : "text-lg"} ${
          tone === "positive" ? "text-emerald-600" : tone === "negative" ? "text-destructive" : ""
        }`}
      >
        {value ?? "—"}
      </div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
