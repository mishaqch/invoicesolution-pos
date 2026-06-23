import { PageHeader } from "@/components/ui/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useProducts, useStockMovements } from "@/lib/queries";
import { qty } from "@/lib/utils";

export default function Movements() {
  const { data, isLoading } = useStockMovements();
  const products = useProducts();
  const productLookup = new Map(products.data?.results.map((p) => [p.id, p]) ?? []);

  return (
    <div className="space-y-4">
      <PageHeader title="Stock movements" subtitle="Append-only ledger. Most recent first." />
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead className="hidden md:table-cell">Type</TableHead>
              <TableHead>Product</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="hidden lg:table-cell">Reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">No movements yet.</TableCell></TableRow>
            ) : (
              data?.results.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(m.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">{m.movement_type}</TableCell>
                  <TableCell>{productLookup.get(m.product)?.name ?? m.product}</TableCell>
                  <TableCell className="text-right font-mono">{qty(m.quantity)}</TableCell>
                  <TableCell className="hidden text-sm lg:table-cell">{m.reason}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
