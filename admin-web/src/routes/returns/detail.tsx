import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useReturn } from "@/lib/queries";

export default function ReturnDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: ret, isLoading } = useReturn(id);

  if (isLoading || !ret) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }

  return (
    <div className="space-y-4">
      <Link
        to="/returns"
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> Back to returns
      </Link>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{ret.return_number}</h1>
        <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
          <Badge variant={ret.fbr_route === "amend" ? "default" : "secondary"}>
            {ret.fbr_route ?? "—"}
          </Badge>
          <span>{ret.return_date}</span>
          {ret.fbr_credit_note_number && (
            <span>· Credit note: {ret.fbr_credit_note_number}</span>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-sm">Reason</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="capitalize">{ret.reason.replace("_", " ")}</div>
            {ret.reason_notes && (
              <div className="text-xs text-muted-foreground">{ret.reason_notes}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Refund</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="capitalize">{ret.refund_method.replace("_", " ")}</div>
            <div className="font-mono text-2xl">Rs {ret.refund_amount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Original invoice</CardTitle></CardHeader>
          <CardContent className="text-sm">
            <Link
              to={`/sales/${ret.original_invoice}`}
              className="font-mono hover:underline"
            >
              {ret.original_invoice.slice(0, 8)}…
            </Link>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Items returned</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Unit price</TableHead>
                <TableHead className="text-right">Tax</TableHead>
                <TableHead className="text-right">Line total</TableHead>
                <TableHead>Restocked</TableHead>
                <TableHead>Movement</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ret.items.map((it) => (
                <TableRow key={it.id}>
                  <TableCell className="font-mono text-xs">
                    {it.product.slice(0, 8)}…
                  </TableCell>
                  <TableCell className="text-right font-mono">{it.quantity}</TableCell>
                  <TableCell className="text-right font-mono">{it.unit_price}</TableCell>
                  <TableCell className="text-right font-mono">{it.tax_amount}</TableCell>
                  <TableCell className="text-right font-mono">{it.line_total}</TableCell>
                  <TableCell>{it.restocked ? "Yes" : "No"}</TableCell>
                  <TableCell className="font-mono text-xs">{it.movement_type}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
