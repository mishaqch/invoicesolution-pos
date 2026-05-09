import { Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  useBranches,
  useCreateManualInvoice,
  useCustomers,
  useProducts,
  useTerminals,
  type ManualInvoiceLine,
  type ManualInvoicePayment,
} from "@/lib/queries";

interface DraftLine {
  product_id: string;
  product_name: string;
  product_sku: string;
  hs_code: string;
  uom_code: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  is_taxable: boolean;
  discount_amount: string;
}

const PAYMENT_METHODS: ManualInvoicePayment["payment_method"][] = [
  "cash", "card", "easypaisa", "jazzcash", "raast",
  "cheque", "bank_transfer", "credit", "store_credit",
];

function rs(amount: number | string): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  return `Rs. ${n.toLocaleString("en-PK", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function uuidv4(): string {
  // RFC4122-ish v4 — fine for client_uuid (server validates uniqueness).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Standalone invoice creation for non-POS workflows: wholesalers,
 * service providers, manual office entries. Builds a cart, computes
 * totals client-side for live feedback, posts to /api/sales/invoices/manual/
 * which atomically creates the invoice and queues the FBR submission.
 *
 * Mirrors the PRAL screens for invoice creation: invoice header (buyer +
 * seller branch), per-line item editor with HS code / UoM / rate / qty,
 * tax rollup, payment method.
 */
export default function NewInvoiceRoute() {
  const navigate = useNavigate();
  const branches = useBranches();
  const terminals = useTerminals();
  const customers = useCustomers();
  const create = useCreateManualInvoice();

  const [branchId, setBranchId] = useState("");
  const [terminalId, setTerminalId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [notes, setNotes] = useState("");
  const [productSearch, setProductSearch] = useState("");
  const [showProductPicker, setShowProductPicker] = useState(false);
  const products = useProducts(productSearch.trim() ? { search: productSearch.trim() } : {});
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [payments, setPayments] = useState<ManualInvoicePayment[]>([
    { payment_method: "cash", amount: "0" },
  ]);
  const [error, setError] = useState<string | null>(null);

  const clientUuidRef = useRef<string>(uuidv4());

  // Pre-pick first branch + terminal once available.
  useEffect(() => {
    if (!branchId && branches.data?.results?.[0]) {
      setBranchId(branches.data.results[0].id);
    }
  }, [branches.data, branchId]);
  useEffect(() => {
    if (!terminalId && terminals.data?.results?.[0]) {
      setTerminalId(terminals.data.results[0].id);
    }
  }, [terminals.data, terminalId]);

  // Live totals — recompute on every cart edit. Mirrors the POS
  // pricing engine's logic at the line-level (qty * unit_price -
  // discount, tax = (line_net) * rate%).
  const totals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    let discount = 0;
    const byRate: Record<string, { taxable: number; tax: number }> = {};
    for (const line of lines) {
      const qty = Number(line.quantity) || 0;
      const price = Number(line.unit_price) || 0;
      const lineDiscount = Number(line.discount_amount) || 0;
      const gross = qty * price;
      const net = Math.max(0, gross - lineDiscount);
      const rate = line.is_taxable ? (Number(line.tax_rate) || 0) : 0;
      const lineTax = (net * rate) / 100;
      subtotal += net;
      tax += lineTax;
      discount += lineDiscount;
      const key = `${rate}`;
      if (!byRate[key]) byRate[key] = { taxable: 0, tax: 0 };
      byRate[key].taxable += net;
      byRate[key].tax += lineTax;
    }
    return {
      subtotal, tax, discount,
      grand: subtotal + tax,
      byRate,
    };
  }, [lines]);

  const totalTendered = useMemo(
    () => payments.reduce((acc, p) => acc + (Number(p.amount) || 0), 0),
    [payments],
  );

  function addProduct(p: any) {
    setLines((curr) => [...curr, {
      product_id: p.id,
      product_name: p.name,
      product_sku: p.sku,
      hs_code: p.hs_code ?? "",
      uom_code: p.uom ?? "PCS",
      quantity: "1",
      unit_price: p.sale_price ?? "0",
      tax_rate: p.tax_rate ?? "18",
      is_taxable: !!p.is_taxable,
      discount_amount: "0",
    }]);
    setShowProductPicker(false);
    setProductSearch("");
  }

  function updateLine(idx: number, patch: Partial<DraftLine>) {
    setLines((curr) => curr.map((line, i) => (i === idx ? { ...line, ...patch } : line)));
  }

  function removeLine(idx: number) {
    setLines((curr) => curr.filter((_, i) => i !== idx));
  }

  function setPaymentField(idx: number, patch: Partial<ManualInvoicePayment>) {
    setPayments((curr) => curr.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function addPayment() {
    setPayments((curr) => [...curr, { payment_method: "cash", amount: "0" }]);
  }
  function removePayment(idx: number) {
    setPayments((curr) => curr.filter((_, i) => i !== idx));
  }

  async function submit() {
    setError(null);
    if (!branchId || !terminalId) {
      setError("Pick a branch and a terminal.");
      return;
    }
    if (lines.length === 0) {
      setError("Add at least one line item.");
      return;
    }
    if (Math.abs(totalTendered - totals.grand) > 0.01) {
      setError(`Payment Rs ${totalTendered.toFixed(2)} doesn't match grand total Rs ${totals.grand.toFixed(2)}.`);
      return;
    }
    try {
      const apiLines: ManualInvoiceLine[] = lines.map((l) => ({
        product: l.product_id,
        quantity: l.quantity,
        unit_price: l.unit_price,
        tax_rate: l.tax_rate,
        is_taxable: l.is_taxable,
        discount_amount: l.discount_amount,
        hs_code: l.hs_code || undefined,
        uom_code: l.uom_code || undefined,
      }));
      const result = await create.mutateAsync({
        branch: branchId,
        terminal: terminalId,
        customer: customerId || null,
        cart_lines: apiLines,
        payments: payments.map((p) => ({
          ...p, amount: String(p.amount),
        })),
        client_uuid: clientUuidRef.current,
        notes: notes || undefined,
      });
      // Take the user to the new invoice's detail page.
      navigate(`/sales/${result.id}`);
    } catch (e: any) {
      setError(e?.message ?? "Save failed.");
    }
  }

  const filteredProducts = products.data?.results ?? [];
  const customerName =
    customers.data?.results?.find((c) => c.id === customerId)?.name ?? "Walk-in";

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <Link to="/sales" className="text-sm text-muted-foreground hover:underline">
            ← Sales
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">New invoice</h1>
          <p className="text-xs text-muted-foreground">
            Manual entry — for wholesalers, service providers, or office staff
            issuing tax invoices outside the POS.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Header</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <div>
              <Label>Branch</Label>
              <Select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
                <option value="">—</option>
                {branches.data?.results?.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </Select>
            </div>
            <div>
              <Label>Terminal / counter</Label>
              <Select value={terminalId} onChange={(e) => setTerminalId(e.target.value)}>
                <option value="">—</option>
                {terminals.data?.results
                  ?.filter((t) => !branchId || t.branch === branchId)
                  .map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
              </Select>
            </div>
            <div>
              <Label>Buyer</Label>
              <Select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                <option value="">Walk-in (unregistered)</option>
                {customers.data?.results?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.ntn ? `· NTN ${c.ntn}` : c.cnic ? `· CNIC ${c.cnic}` : ""}
                  </option>
                ))}
              </Select>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Live totals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span className="font-mono">{rs(totals.subtotal)}</span>
            </div>
            {totals.discount > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Discount</span>
                <span className="font-mono">−{rs(totals.discount)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tax</span>
              <span className="font-mono">{rs(totals.tax)}</span>
            </div>
            <div className="border-t pt-1.5 flex items-baseline justify-between text-base font-semibold">
              <span>Grand total</span>
              <span className="font-mono">{rs(totals.grand)}</span>
            </div>
            {Object.entries(totals.byRate).filter(([rate]) => rate !== "0").length > 0 && (
              <div className="mt-2 border-t pt-2">
                <div className="text-xs text-muted-foreground">By rate band</div>
                {Object.entries(totals.byRate).map(([rate, v]) => (
                  <div key={rate} className="flex justify-between text-xs">
                    <span>{rate}%</span>
                    <span className="font-mono">{rs(v.taxable)} → tax {rs(v.tax)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm">Items</CardTitle>
          <Button
            size="sm" variant="outline"
            onClick={() => setShowProductPicker((v) => !v)}
          >
            <Plus className="mr-1 h-4 w-4" /> Add line
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {showProductPicker && (
            <div className="border-b p-3">
              <div className="relative max-w-md">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Search by SKU, barcode, name…"
                  value={productSearch}
                  autoFocus
                  onChange={(e) => setProductSearch(e.target.value)}
                />
              </div>
              <div className="mt-2 max-h-56 overflow-y-auto rounded-md border bg-background">
                {filteredProducts.length === 0 ? (
                  <p className="p-3 text-xs text-muted-foreground">
                    {productSearch ? "No matches." : "Start typing to find a product."}
                  </p>
                ) : (
                  <ul className="divide-y">
                    {filteredProducts.slice(0, 20).map((p: any) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          onClick={() => addProduct(p)}
                          className="flex w-full items-baseline justify-between p-2 text-left text-sm hover:bg-muted"
                        >
                          <span>
                            <span className="font-mono text-xs text-muted-foreground">{p.sku}</span>{" "}
                            {p.name}
                          </span>
                          <span className="font-mono">{rs(p.sale_price)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {lines.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No lines yet. Click "Add line" to pick a product.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-xs">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">SKU / name</th>
                  <th className="px-3 py-2 text-left font-medium">HS code</th>
                  <th className="px-3 py-2 text-left font-medium">UoM</th>
                  <th className="px-3 py-2 text-right font-medium">Qty</th>
                  <th className="px-3 py-2 text-right font-medium">Rate (Rs)</th>
                  <th className="px-3 py-2 text-right font-medium">Tax %</th>
                  <th className="px-3 py-2 text-right font-medium">Discount</th>
                  <th className="px-3 py-2 text-right font-medium">Line total</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, idx) => {
                  const qty = Number(line.quantity) || 0;
                  const price = Number(line.unit_price) || 0;
                  const lineDiscount = Number(line.discount_amount) || 0;
                  const net = Math.max(0, qty * price - lineDiscount);
                  const rate = line.is_taxable ? (Number(line.tax_rate) || 0) : 0;
                  const lineTotal = net * (1 + rate / 100);
                  return (
                    <tr key={idx} className="border-b">
                      <td className="px-3 py-2">
                        <div className="font-mono text-xs text-muted-foreground">{line.product_sku}</div>
                        <div>{line.product_name}</div>
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          value={line.hs_code}
                          onChange={(e) => updateLine(idx, { hs_code: e.target.value })}
                          className="h-8 w-24 text-xs"
                          placeholder="0101.2100"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          value={line.uom_code}
                          onChange={(e) => updateLine(idx, { uom_code: e.target.value })}
                          className="h-8 w-16 text-xs"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          value={line.quantity}
                          onChange={(e) => updateLine(idx, { quantity: e.target.value })}
                          className="h-8 w-20 text-right text-xs"
                          inputMode="decimal"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          value={line.unit_price}
                          onChange={(e) => updateLine(idx, { unit_price: e.target.value })}
                          className="h-8 w-24 text-right text-xs"
                          inputMode="decimal"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          value={line.tax_rate}
                          onChange={(e) => updateLine(idx, { tax_rate: e.target.value })}
                          className="h-8 w-16 text-right text-xs"
                          inputMode="decimal"
                          disabled={!line.is_taxable}
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Input
                          value={line.discount_amount}
                          onChange={(e) => updateLine(idx, { discount_amount: e.target.value })}
                          className="h-8 w-20 text-right text-xs"
                          inputMode="decimal"
                        />
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{rs(lineTotal)}</td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => removeLine(idx)}
                          className="text-muted-foreground hover:text-destructive"
                          aria-label="Remove line"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Payments</CardTitle>
            <Button size="sm" variant="outline" onClick={addPayment}>
              <Plus className="mr-1 h-4 w-4" /> Add payment
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {payments.map((p, idx) => (
              <div key={idx} className="grid grid-cols-12 gap-2">
                <Select
                  value={p.payment_method}
                  onChange={(e) => setPaymentField(idx, {
                    payment_method: e.target.value as ManualInvoicePayment["payment_method"],
                  })}
                  className="col-span-5"
                >
                  {PAYMENT_METHODS.map((m) => (
                    <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                  ))}
                </Select>
                <Input
                  value={p.amount}
                  onChange={(e) => setPaymentField(idx, { amount: e.target.value })}
                  className="col-span-5 text-right font-mono"
                  inputMode="decimal"
                  placeholder="0.00"
                />
                <button
                  onClick={() => removePayment(idx)}
                  className="col-span-2 rounded-md text-muted-foreground hover:text-destructive"
                  aria-label="Remove payment"
                >
                  <Trash2 className="mx-auto h-4 w-4" />
                </button>
              </div>
            ))}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                if (payments.length === 1) {
                  setPaymentField(0, { amount: totals.grand.toFixed(2) });
                }
              }}
              disabled={payments.length !== 1}
            >
              Match grand total to first payment
            </Button>
            <div className="flex justify-between border-t pt-2 text-sm">
              <span className="text-muted-foreground">Tendered</span>
              <span className={`font-mono ${
                Math.abs(totalTendered - totals.grand) < 0.01
                  ? "text-green-700" : "text-amber-700"
              }`}>
                {rs(totalTendered)}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes for this invoice (visible in admin only)…"
              className="w-full rounded-md border bg-background px-2 py-1 text-sm"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Buyer: <Badge variant="outline">{customerName}</Badge>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              On submit, the invoice is created and queued for FBR
              submission. The FBR invoice number appears on the detail
              page once PRAL responds (usually within seconds in sandbox,
              up to a few seconds in production).
            </p>
          </CardContent>
        </Card>
      </div>

      {error && (
        <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => navigate("/sales")}>Cancel</Button>
        <Button onClick={submit} disabled={create.isPending}>
          {create.isPending ? "Submitting…" : "Create invoice & submit to FBR"}
        </Button>
      </div>
    </div>
  );
}
