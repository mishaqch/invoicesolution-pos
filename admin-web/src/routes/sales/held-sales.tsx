import { Link } from "react-router-dom";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useInvoices } from "@/lib/queries";
import { money } from "@/lib/utils";

export default function HeldSalesAdminList() {
  const { data, isLoading } = useInvoices({ held: "true" });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Held invoices</h1>
      <p className="text-sm text-muted-foreground">
        Draft invoices held across all terminals — manager view. Recall
        happens on the cashier's terminal.
      </p>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Label</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead>Items</TableHead>
              <TableHead className="text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">
                No held sales right now.
              </TableCell></TableRow>
            ) : (
              data?.results.map((i) => (
                <TableRow key={i.id}>
                  <TableCell>{i.held_label ?? "(unlabelled)"}</TableCell>
                  <TableCell className="font-mono text-xs">
                    <Link to={`/sales/${i.id}`} className="hover:underline">
                      {i.local_invoice_number}
                    </Link>
                  </TableCell>
                  <TableCell>{i.items.length}</TableCell>
                  <TableCell className="text-right font-mono">{money(i.grand_total)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
