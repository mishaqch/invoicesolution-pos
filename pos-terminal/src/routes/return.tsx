import { ArrowLeft, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";
import { Money } from "@/lib/money";
import { newClientUuid } from "@/lib/uuid";
import { useSessionStore } from "@/stores/session";
import { usePosContext } from "@/features/sale/usePosContext";

interface InvoiceLine {
  id: string;
  line_number: number;
  product: string;
  product_name: string;
  product_sku: string;
  uom_code: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
  line_total: string;
  is_cancelled: boolean;
}

interface AdminInvoice {
  id: string;
  local_invoice_number: string;
  fbr_invoice_number: string | null;
  invoice_date: string;
  buyer_name: string | null;
  customer: string | null;
  grand_total: string;
  status: string;
  items: InvoiceLine[];
}

const REASONS = [
  { code: "damaged", label: "Damaged" },
  { code: "wrong_item", label: "Wrong item" },
  { code: "customer_changed_mind", label: "Customer changed mind" },
  { code: "expired", label: "Expired" },
  { code: "other", label: "Other" },
];

const REFUND_METHODS = [
  { code: "cash", label: "Cash" },
  { code: "store_credit", label: "Store credit" },
  { code: "card_reversal", label: "Card reversal" },
  { code: "wallet_reversal", label: "Wallet reversal" },
  { code: "bank_transfer", label: "Bank transfer" },
];

export default function ReturnRoute() {
  const navigate = useNavigate();
  const ctx = usePosContext();
  const user = useSessionStore((s) => s.user);

  // Step 1 — find original invoice
  const [searchLocal, setSearchLocal] = useState("");
  const [searchFbr, setSearchFbr] = useState("");
  const [matches, setMatches] = useState<AdminInvoice[]>([]);
  const [picked, setPicked] = useState<AdminInvoice | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  // Step 2 — pick lines
  const [pickedLines, setPickedLines] = useState<Record<string, string>>({});

  // Step 3+4 — reason / refund
  const [reason, setReason] = useState(REASONS[0].code);
  const [reasonNotes, setReasonNotes] = useState("");
  const [refundMethod, setRefundMethod] = useState(REFUND_METHODS[0].code);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    setSearchError(null);
    setSearching(true);
    try {
      const params = new URLSearchParams();
      if (searchLocal) params.set("local", searchLocal);
      if (searchFbr) params.set("fbr", searchFbr);
      const data = await api<{ results: AdminInvoice[] }>(
        `/returns/find-invoice/?${params.toString()}`,
      );
      setMatches(data.results);
      if (data.results.length === 0) setSearchError("No matches.");
    } catch (err) {
      setSearchError(err instanceof ApiError ? `API ${err.status}` : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  // Compute total refund as cashier picks quantities.
  const totalRefund = useMemo(() => {
    if (!picked) return Money.zero();
    return picked.items.reduce((acc, line) => {
      const qty = pickedLines[line.id];
      if (!qty) return acc;
      const q = Money.fromStr(qty);
      const unit = Money.fromStr(line.unit_price);
      const taxPerUnit = line.quantity !== "0"
        ? Money.fromStr(line.tax_amount).mulScalar(
            (Number(qty) / Number(line.quantity)).toString(),
          )
        : Money.zero();
      // simpler: tax_amount * (qty / orig_qty) — use ratio for safety
      const lineNet = unit.mulScalar(qty);
      const lineTotal = lineNet.add(taxPerUnit);
      return acc.add(lineTotal);
    }, Money.zero());
  }, [picked, pickedLines]);

  async function submit() {
    if (!picked || !ctx.branch || !ctx.terminal || !user) return;
    const items = Object.entries(pickedLines)
      .filter(([, qty]) => qty && Number(qty) > 0)
      .map(([sale_item_id, qty]) => ({
        original_sale_item_id: sale_item_id,
        quantity: qty,
      }));
    if (items.length === 0) {
      setError("Pick at least one line and quantity.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const ret = await api<{ id: string; return_number: string; refund_amount: string }>(
        "/returns/",
        {
          method: "POST",
          body: JSON.stringify({
            original_invoice: picked.id,
            branch: ctx.branch.id,
            terminal: ctx.terminal.id,
            items,
            reason,
            reason_notes: reasonNotes,
            refund_method: refundMethod,
            refund_data: {},
            client_uuid: newClientUuid(),
          }),
        },
      );
      // Drawer fires for cash refunds.
      if (refundMethod === "cash") void window.api.drawer.open();
      window.alert(
        `Return ${ret.return_number} processed. Refund: Rs ${ret.refund_amount}`,
      );
      navigate("/sale", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? `API ${err.status}` : "Return failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate("/sale", { replace: true })}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to sale
        </button>
        <div className="text-sm font-medium">Return / refund</div>
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 gap-4 p-6 md:grid-cols-12">
        {/* Step 1 */}
        <section className="md:col-span-4">
          <Card>
            <CardHeader><CardTitle className="text-sm">1. Find original invoice</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label>Local invoice #</Label>
                <Input value={searchLocal} onChange={(e) => setSearchLocal(e.target.value)} />
              </div>
              <div>
                <Label>FBR #</Label>
                <Input value={searchFbr} onChange={(e) => setSearchFbr(e.target.value)} />
              </div>
              <Button
                size="sm" disabled={searching || (!searchLocal && !searchFbr)}
                onClick={search}
              >
                <Search className="mr-1 h-4 w-4" /> Search
              </Button>
              {searchError && <p className="text-xs text-destructive">{searchError}</p>}

              {matches.length > 0 && (
                <div className="max-h-64 space-y-1 overflow-auto">
                  {matches.map((m) => (
                    <button
                      key={m.id} type="button"
                      onClick={() => { setPicked(m); setPickedLines({}); }}
                      className={`w-full rounded-md border p-2 text-left text-xs hover:bg-muted ${
                        picked?.id === m.id ? "bg-muted" : ""
                      }`}
                    >
                      <div className="font-mono">{m.local_invoice_number}</div>
                      <div className="text-muted-foreground">
                        {m.invoice_date} · Rs {m.grand_total} · {m.status}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* Step 2 */}
        <section className="md:col-span-5">
          <Card>
            <CardHeader><CardTitle className="text-sm">2. Pick lines and quantities</CardTitle></CardHeader>
            <CardContent>
              {!picked ? (
                <p className="text-sm text-muted-foreground">Pick an original invoice first.</p>
              ) : (
                <div className="space-y-2">
                  {picked.items.map((line) => (
                    <div key={line.id} className="flex items-center gap-2 rounded-md border p-2">
                      <div className="flex-1">
                        <div className="text-sm">{line.product_name}</div>
                        <div className="text-xs text-muted-foreground">
                          Sold qty: {line.quantity} · Rs {line.unit_price} ea
                        </div>
                      </div>
                      <input
                        type="number"
                        min="0" step="0.01" max={line.quantity}
                        value={pickedLines[line.id] ?? ""}
                        onChange={(e) =>
                          setPickedLines({ ...pickedLines, [line.id]: e.target.value })
                        }
                        className="w-20 rounded-md border bg-background px-2 py-1 text-right text-sm"
                        disabled={line.is_cancelled}
                      />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* Step 3 + 4 */}
        <section className="md:col-span-3 space-y-3">
          <Card>
            <CardHeader><CardTitle className="text-sm">3. Reason</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Select value={reason} onChange={(e) => setReason(e.target.value)}>
                {REASONS.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
              </Select>
              <textarea
                rows={2} placeholder="Notes (optional)"
                value={reasonNotes}
                onChange={(e) => setReasonNotes(e.target.value)}
                className="w-full rounded-md border bg-background px-2 py-1 text-sm"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm">4. Refund method</CardTitle></CardHeader>
            <CardContent>
              <Select value={refundMethod} onChange={(e) => setRefundMethod(e.target.value)}>
                {REFUND_METHODS.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
              </Select>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm">Refund</CardTitle></CardHeader>
            <CardContent>
              <div className="font-mono text-2xl">Rs {totalRefund.display()}</div>
            </CardContent>
          </Card>

          <Button
            className="w-full h-12"
            disabled={submitting || !picked || totalRefund.isZero()}
            onClick={submit}
          >
            {submitting ? "Processing…" : "Confirm return"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </section>
      </main>
    </div>
  );
}
