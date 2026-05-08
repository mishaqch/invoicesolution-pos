import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useProducts, useStockMovements } from "@/lib/queries";

export default function Movements() {
  const { data, isLoading } = useStockMovements();
  const products = useProducts();
  const productLookup = new Map(products.data?.results.map((p) => [p.id, p]) ?? []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Stock movements</h1>
      <p className="text-sm text-muted-foreground">Append-only ledger. Most recent first.</p>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Product</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead>Reason</TableHead>
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
                  <TableCell className="font-mono text-xs">{m.movement_type}</TableCell>
                  <TableCell>{productLookup.get(m.product)?.name ?? m.product}</TableCell>
                  <TableCell className="text-right font-mono">{m.quantity}</TableCell>
                  <TableCell className="text-sm">{m.reason}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
