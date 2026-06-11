import { Link } from "react-router-dom";

import { PageHeader } from "@/components/ui/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useInvoices } from "@/lib/queries";
import { money } from "@/lib/utils";

export default function HeldSalesAdminList() {
  const { data, isLoading } = useInvoices({ held: "true" });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Held invoices"
        subtitle="Draft invoices held across all terminals — manager view. Recall happens on the cashier's terminal."
      />
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="hidden md:table-cell">Label</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead className="hidden sm:table-cell">Items</TableHead>
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
                  <TableCell className="hidden md:table-cell">{i.held_label ?? "(unlabelled)"}</TableCell>
                  <TableCell className="font-mono text-xs">
                    <Link to={`/sales/${i.id}`} className="hover:underline">
                      {i.local_invoice_number}
                    </Link>
                    {/* Label surfaced inline where its column is hidden. */}
                    <span className="block font-sans text-[11px] text-muted-foreground md:hidden">
                      {i.held_label ?? "(unlabelled)"}
                    </span>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">{i.items.length}</TableCell>
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
