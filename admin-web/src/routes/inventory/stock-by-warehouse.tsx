/**
 * Stock by warehouse (Digital-Invoicing).
 *
 * Per-item on-hand for one warehouse: how much you have right now. From here a
 * distributor sets opening stock or records stock-in (a fresh arrival) per
 * item — both post to the adjustments endpoint with the warehouse set, so the
 * warehouse-keyed StockLevel updates and sales draw it down.
 *
 * POS tenants never see this (gated by the `warehouses` module + DI mode);
 * their branch-keyed "Stock by branch" page is untouched.
 */
import { PackagePlus, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useDeleteStockLevel,
  usePostAdjustment,
  useProducts,
  useStockLevels,
  useWarehouses,
} from "@/lib/queries";

/** Short, column-friendly label for the verbose PRAL saleType string. */
function shortSaleType(s: string | null | undefined): string {
  if (!s) return "—";
  const map: Record<string, string> = {
    "Goods at standard rate (default)": "Standard",
    "3rd Schedule Goods": "3rd Schedule",
    "Goods at Reduced Rate": "Reduced",
    "Goods at zero-rate": "Zero-rated",
    "Exempt goods": "Exempt",
    "Electric Vehicle": "Electric Vehicle",
  };
  return map[s] ?? s;
}

export default function StockByWarehouse() {
  const warehouses = useWarehouses();
  const products = useProducts();
  const toast = useToast();

  const whRows = warehouses.data?.results ?? [];
  // Default to the tenant default warehouse, else the first.
  const defaultWh = whRows.find((w) => w.is_default)?.id ?? whRows[0]?.id ?? "";
  const [warehouse, setWarehouse] = useState<string>("");
  const activeWh = warehouse || defaultWh;

  const { data, isLoading } = useStockLevels(activeWh ? { warehouse: activeWh } : {});
  const productLookup = useMemo(
    () => new Map(products.data?.results.map((p) => [p.id, p]) ?? []),
    [products.data],
  );

  const selectedWh = whRows.find((w) => w.id === activeWh);

  // Per-row stock edit / remove. Both post an opening_balance adjustment, which
  // the backend now treats as an ABSOLUTE set (idempotent) — so "edit" corrects
  // the on-hand to a typed value and "remove" sets it to 0.
  const post = usePostAdjustment();
  const delStock = useDeleteStockLevel();

  async function editQuantity(productId: string, name: string, current: string) {
    if (!selectedWh) return;
    const input = window.prompt(`Set on-hand quantity for "${name}":`, current);
    if (input === null) return;
    const qty = input.trim();
    if (qty === "" || Number.isNaN(Number(qty)) || Number(qty) < 0) {
      toast.show({ message: "Enter a valid non-negative number.", variant: "destructive" });
      return;
    }
    try {
      await post.mutateAsync({
        branch: selectedWh.branch, warehouse: activeWh, product: productId,
        movement_type: "opening_balance", quantity: qty,
        reason: "Manual stock correction",
      });
      toast.show({ message: `Stock for "${name}" set to ${qty}.`, variant: "success" });
    } catch (err) {
      toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
    }
  }

  async function removeStock(s: { id: string; product: string; quantity: string }, name: string) {
    if (!selectedWh) return;
    if (!window.confirm(`Remove "${name}" from this warehouse's stock list? (Any on-hand is zeroed; the movement history is kept for audit.)`)) return;
    try {
      // Zero it first if it still holds stock (the delete endpoint refuses a
      // non-zero row), then delete the now-empty line so it leaves the list.
      if (Number(s.quantity) !== 0) {
        await post.mutateAsync({
          branch: selectedWh.branch, warehouse: activeWh, product: s.product,
          movement_type: "opening_balance", quantity: "0",
          reason: "Stock removed (set to 0)",
        });
      }
      await delStock.mutateAsync(s.id);
      toast.show({ message: `"${name}" removed from this warehouse.`, variant: "info" });
    } catch (err) {
      toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Stock by warehouse" />

      <div className="flex w-full items-end gap-3 sm:max-w-md">
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="wh">Warehouse</Label>
          <Select id="wh" value={activeWh} onChange={(e) => setWarehouse(e.target.value)}>
            {whRows.length === 0 && <option value="">No warehouses yet</option>}
            {whRows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} — {w.branch_name}{w.is_default ? " (default)" : ""}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {activeWh && selectedWh && (
        <StockInCard
          warehouseId={activeWh}
          branchId={selectedWh.branch}
          onSaved={() => toast.show({ message: "Stock updated.", variant: "success" })}
        />
      )}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead className="hidden lg:table-cell">SKU</TableHead>
              <TableHead className="hidden md:table-cell">HS code</TableHead>
              <TableHead className="hidden lg:table-cell">UoM</TableHead>
              <TableHead className="hidden xl:table-cell">Sale type</TableHead>
              <TableHead className="text-right">On hand</TableHead>
              <TableHead className="w-px" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {!activeWh ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">Add a warehouse first.</TableCell></TableRow>
            ) : isLoading ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : (data?.results.length ?? 0) === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">No stock yet in this warehouse.</TableCell></TableRow>
            ) : (
              data!.results.map((s) => {
                // FBR fields come straight from the stock row now (the API embeds
                // the product's hs_code / uom / sale_type), falling back to the
                // product lookup for name/sku on older payloads.
                const p = productLookup.get(s.product);
                const name = s.product_name ?? p?.name ?? s.product;
                const sku = s.product_sku ?? p?.sku ?? "";
                const fbrMissing = !s.hs_code;
                return (
                  <TableRow key={s.id}>
                    <TableCell>
                      {name}
                      {sku && (
                        <span className="block font-mono text-[11px] text-muted-foreground lg:hidden">{sku}</span>
                      )}
                      {fbrMissing && (
                        <span className="block text-[11px] text-warning-soft-foreground">No HS code — set it on the product before invoicing</span>
                      )}
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs lg:table-cell">{sku}</TableCell>
                    <TableCell className="hidden font-mono text-xs md:table-cell">{s.hs_code || "—"}</TableCell>
                    <TableCell className="hidden text-xs lg:table-cell">{s.uom || "—"}</TableCell>
                    <TableCell className="hidden text-xs xl:table-cell">{shortSaleType(s.sale_type)}</TableCell>
                    <TableCell className="text-right font-mono">{s.quantity}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" title="Correct on-hand quantity"
                          onClick={() => editQuantity(s.product, name, s.quantity)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" title="Remove from stock list"
                          onClick={() => removeStock(s, name)}>
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

/** Inline "set opening balance / add stock" for the selected warehouse. */
function StockInCard({
  warehouseId,
  branchId,
  onSaved,
}: {
  warehouseId: string;
  branchId: string;
  onSaved: () => void;
}) {
  const products = useProducts();
  const post = usePostAdjustment();

  const [product, setProduct] = useState("");
  const [movementType, setMovementType] = useState("opening_balance");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post.mutateAsync({
        branch: branchId,
        warehouse: warehouseId,
        product,
        movement_type: movementType,
        quantity,
        reason: reason || (movementType === "opening_balance" ? "Opening balance" : "Stock in"),
      });
      setQuantity("");
      setReason("");
      onSaved();
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <PackagePlus className="h-4 w-4" /> Add / set stock
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="sw-product">Product *</Label>
            <Select id="sw-product" value={product} onChange={(e) => setProduct(e.target.value)} required>
              <option value="">— Select —</option>
              {products.data?.results.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sw-type">Type *</Label>
            <Select id="sw-type" value={movementType} onChange={(e) => setMovementType(e.target.value)}>
              <option value="opening_balance">Opening balance</option>
              <option value="adjustment_in">Stock in (add)</option>
              <option value="adjustment_out">Stock out (remove)</option>
              <option value="damage">Damage</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sw-qty">Quantity *</Label>
            <NumberInput id="sw-qty" mode="decimal" value={quantity} onChange={setQuantity} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sw-reason">Reason</Label>
            <Input id="sw-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="optional note" />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" loading={post.isPending}>
              <Plus className="mr-2 h-4 w-4" /> {post.isPending ? "Saving…" : "Save"}
            </Button>
            {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
