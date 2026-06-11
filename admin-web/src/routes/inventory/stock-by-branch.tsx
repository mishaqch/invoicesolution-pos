import { useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranches, useProducts, useStockLevels } from "@/lib/queries";

export default function StockByBranch() {
  const branches = useBranches();
  const products = useProducts();
  const [branch, setBranch] = useState<string>("");

  const { data, isLoading } = useStockLevels(branch ? { branch } : {});

  const productLookup = new Map(products.data?.results.map((p) => [p.id, p]) ?? []);

  return (
    <div className="space-y-4">
      <PageHeader title="Stock by branch" />
      <div className="flex w-full items-end gap-3 sm:max-w-md">
        <div className="flex-1 space-y-1.5">
          <label className="text-sm font-medium">Branch</label>
          <Select value={branch} onChange={(e) => setBranch(e.target.value)}>
            <option value="">All branches</option>
            {branches.data?.results.map((b) => (
              <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
            ))}
          </Select>
        </div>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead className="hidden lg:table-cell">SKU</TableHead>
              <TableHead className="text-right">Quantity</TableHead>
              <TableHead className="hidden text-right md:table-cell">Reorder level</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">No stock yet for this branch.</TableCell></TableRow>
            ) : (
              data?.results.map((s) => {
                const p = productLookup.get(s.product);
                return (
                  <TableRow key={s.id}>
                    <TableCell>
                      {p?.name ?? s.product}
                      {p?.sku && (
                        <span className="block font-mono text-[11px] text-muted-foreground lg:hidden">
                          {p.sku}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs lg:table-cell">{p?.sku}</TableCell>
                    <TableCell className="text-right font-mono">{s.quantity}</TableCell>
                    <TableCell className="hidden text-right font-mono md:table-cell">{s.reorder_level ?? "—"}</TableCell>
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
