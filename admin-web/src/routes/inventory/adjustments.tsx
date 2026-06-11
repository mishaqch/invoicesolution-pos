import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { useBranches, usePostAdjustment, useProducts } from "@/lib/queries";

export default function Adjustments() {
  const branches = useBranches();
  const products = useProducts();
  const post = usePostAdjustment();

  const [branch, setBranch] = useState("");
  const [product, setProduct] = useState("");
  const [movementType, setMovementType] = useState("opening_balance");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    try {
      await post.mutateAsync({
        branch, product, movement_type: movementType,
        quantity, reason,
      });
      setDone(true);
      setQuantity("");
      setReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Stock adjustment" />

      <Card>
        <CardHeader>
          <CardTitle>New adjustment</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="branch">Branch *</Label>
              <Select id="branch" value={branch} onChange={(e) => setBranch(e.target.value)} required>
                <option value="">— Select —</option>
                {branches.data?.results.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="product">Product *</Label>
              <Select id="product" value={product} onChange={(e) => setProduct(e.target.value)} required>
                <option value="">— Select —</option>
                {products.data?.results.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mt">Movement type *</Label>
              <Select id="mt" value={movementType} onChange={(e) => setMovementType(e.target.value)}>
                <option value="opening_balance">Opening balance</option>
                <option value="adjustment_in">Adjustment in</option>
                <option value="adjustment_out">Adjustment out</option>
                <option value="damage">Damage</option>
                <option value="expiry">Expiry</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qty">Quantity *</Label>
              <NumberInput id="qty" mode="decimal" value={quantity} onChange={setQuantity} required />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="reason">Reason *</Label>
              <Input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" loading={post.isPending}>
                {post.isPending ? "Submitting…" : "Submit"}
              </Button>
              {done && <span className="ml-3 text-sm text-green-700">Submitted.</span>}
              {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
