import { PackagePlus, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranches,
  useCreateGoodsReceipt,
  useGoodsReceipts,
  usePostGoodsReceipt,
  useProducts,
  useSuppliers,
} from "@/lib/queries";

interface DraftLine {
  product: string;
  quantity: string;
  cost_price: string;
  batch_number: string;
  expiry_date: string;
}

const blankLine: DraftLine = { product: "", quantity: "", cost_price: "", batch_number: "", expiry_date: "" };

export default function ReceiveStock() {
  const { data: branchData } = useBranches();
  const branches = branchData?.results ?? [];
  const { data: supplierData } = useSuppliers({ page_size: "200" });
  const suppliers = supplierData?.results ?? [];
  const { data: productData } = useProducts({ page_size: "200" });
  const products = productData?.results ?? [];

  const create = useCreateGoodsReceipt();
  const post = usePostGoodsReceipt();
  const { data: grnData } = useGoodsReceipts({ page_size: "20" });
  const receipts = grnData?.results ?? [];

  const today = new Date().toISOString().slice(0, 10);
  const [supplier, setSupplier] = useState("");
  const [branch, setBranch] = useState("");
  const [reference, setReference] = useState("");
  const [receivedDate, setReceivedDate] = useState(today);
  const [lines, setLines] = useState<DraftLine[]>([{ ...blankLine }]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const productById = useMemo(
    () => Object.fromEntries(products.map((p) => [p.id, p])),
    [products],
  );

  function setLine(i: number, patch: Partial<DraftLine>) {
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  }

  async function submit(thenPost: boolean) {
    setError(null); setMsg(null);
    const effectiveBranch = branch || branches[0]?.id || "";
    if (!supplier) { setError("Pick a supplier."); return; }
    if (!effectiveBranch) { setError("Pick a branch."); return; }
    const valid = lines.filter((l) => l.product && Number(l.quantity) > 0);
    if (valid.length === 0) { setError("Add at least one line with a product and quantity."); return; }
    // Batch-tracked products require a batch number.
    for (const l of valid) {
      if (productById[l.product]?.is_batch_tracked && !l.batch_number.trim()) {
        setError(`${productById[l.product]?.name} is batch-tracked — enter a batch number.`);
        return;
      }
    }
    try {
      const grn = await create.mutateAsync({
        supplier, branch: effectiveBranch,
        reference: reference || null,
        received_date: receivedDate,
        items: valid.map((l) => ({
          product: l.product,
          quantity: l.quantity,
          cost_price: l.cost_price || null,
          batch_number: l.batch_number || null,
          manufactured_date: null,
          expiry_date: l.expiry_date || null,
        })),
      });
      if (thenPost) {
        await post.mutateAsync(grn.id);
        setMsg("Stock received and posted — inventory updated.");
      } else {
        setMsg("Draft saved. Post it to move stock into inventory.");
      }
      // Reset the form.
      setReference(""); setLines([{ ...blankLine }]);
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Receive stock</h1>
        <p className="text-sm text-muted-foreground">
          Record a delivery from a supplier. Posting creates batches (with expiry) and adds the stock to inventory.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>New goods receipt</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="Supplier" id="grn_supplier">
              <Select id="grn_supplier" value={supplier} onChange={(e) => setSupplier(e.target.value)}>
                <option value="">Select…</option>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
            {branches.length > 1 && (
              <Field label="Branch" id="grn_branch">
                <Select id="grn_branch" value={branch || branches[0]?.id || ""} onChange={(e) => setBranch(e.target.value)}>
                  {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </Select>
              </Field>
            )}
            <Field label="Supplier invoice #" id="grn_ref">
              <Input id="grn_ref" value={reference} onChange={(e) => setReference(e.target.value)} />
            </Field>
            <Field label="Received date" id="grn_date">
              <Input id="grn_date" type="date" value={receivedDate} onChange={(e) => setReceivedDate(e.target.value)} />
            </Field>
          </div>

          {/* Lines */}
          <div className="rounded-md border">
            <div className="grid grid-cols-[2fr_0.8fr_1fr_1fr_1fr_auto] gap-2 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
              <span>Product</span><span>Qty</span><span>Cost</span><span>Batch #</span><span>Expiry</span><span></span>
            </div>
            {lines.map((l, i) => {
              const needsBatch = l.product ? productById[l.product]?.is_batch_tracked : false;
              return (
                <div key={i} className="grid grid-cols-[2fr_0.8fr_1fr_1fr_1fr_auto] items-center gap-2 border-b px-3 py-2 last:border-0">
                  <Select value={l.product} onChange={(e) => setLine(i, { product: e.target.value })}>
                    <option value="">Select product…</option>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </Select>
                  <NumberInput mode="decimal" value={l.quantity} onChange={(v) => setLine(i, { quantity: v })} aria-label="Quantity" />
                  <NumberInput mode="decimal" value={l.cost_price} onChange={(v) => setLine(i, { cost_price: v })} aria-label="Cost" />
                  <Input
                    value={l.batch_number}
                    onChange={(e) => setLine(i, { batch_number: e.target.value })}
                    placeholder={needsBatch ? "required" : "—"}
                    disabled={!needsBatch}
                  />
                  <Input type="date" value={l.expiry_date} onChange={(e) => setLine(i, { expiry_date: e.target.value })} disabled={!needsBatch} />
                  <Button type="button" size="icon" variant="ghost" onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              );
            })}
          </div>
          <Button type="button" size="sm" variant="outline" className="gap-1" onClick={() => setLines((ls) => [...ls, { ...blankLine }])}>
            <Plus className="h-4 w-4" /> Add line
          </Button>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {msg && <p className="text-sm text-success-soft-foreground">{msg}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" loading={create.isPending && !post.isPending} onClick={() => submit(false)}>
              Save draft
            </Button>
            <Button className="gap-1" loading={post.isPending} onClick={() => submit(true)}>
              <PackagePlus className="h-4 w-4" /> Receive &amp; post
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Recent receipts */}
      <Card>
        <CardHeader><CardTitle>Recent receipts</CardTitle></CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead><TableHead>Supplier</TableHead>
                  <TableHead>Reference</TableHead><TableHead>Branch</TableHead><TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {receipts.length === 0 ? (
                  <TableRow><TableCell colSpan={5} className="py-6 text-center text-muted-foreground">No receipts yet.</TableCell></TableRow>
                ) : (
                  receipts.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.received_date}</TableCell>
                      <TableCell className="font-medium">{r.supplier_name ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{r.reference ?? "—"}</TableCell>
                      <TableCell className="text-muted-foreground">{r.branch_name ?? "—"}</TableCell>
                      <TableCell>
                        {r.status === "posted"
                          ? <Badge variant="secondary">Posted</Badge>
                          : <Badge variant="warning">Draft</Badge>}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
