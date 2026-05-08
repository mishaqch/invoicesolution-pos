import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCancelInvoice, useInvoice } from "@/lib/queries";

export default function InvoiceDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: invoice, isLoading } = useInvoice(id);
  const cancel = useCancelInvoice();
  const [showConfirm, setShowConfirm] = useState(false);
  const [reason, setReason] = useState("");

  if (isLoading || !invoice) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }

  return (
    <div className="space-y-4">
      <Link
        to="/sales"
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> Back to sales
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {invoice.local_invoice_number}
          </h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant={statusVariant(invoice.status)}>{invoice.status}</Badge>
            <span>{invoice.invoice_date}</span>
            {invoice.fbr_invoice_number && (
              <span>· FBR {invoice.fbr_invoice_number}</span>
            )}
          </div>
        </div>
        {invoice.status !== "cancelled" && invoice.status !== "finalized" && (
          <Button variant="destructive" onClick={() => setShowConfirm(true)}>
            Cancel sale
          </Button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-sm">Buyer</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {invoice.buyer_name ? (
              <>
                <div>{invoice.buyer_name}</div>
                {invoice.buyer_phone && <div className="text-muted-foreground">{invoice.buyer_phone}</div>}
              </>
            ) : (
              <span className="text-muted-foreground">Walk-in</span>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Totals</CardTitle></CardHeader>
          <CardContent className="text-sm">
            <Row k="Subtotal" v={`Rs ${invoice.subtotal}`} />
            <Row k="Discount" v={`- Rs ${invoice.discount_total}`} muted />
            <Row k="Tax" v={`Rs ${invoice.tax_total}`} />
            <Row k="Grand total" v={`Rs ${invoice.grand_total}`} bold />
            <Row k="Paid" v={`Rs ${invoice.paid_total}`} />
            <Row k="Change" v={`Rs ${invoice.change_given}`} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Payments</CardTitle></CardHeader>
          <CardContent className="text-sm">
            {invoice.payments.length === 0 ? (
              <span className="text-muted-foreground">None</span>
            ) : (
              <ul className="space-y-1">
                {invoice.payments.map((p) => (
                  <li key={p.id} className="flex justify-between font-mono">
                    <span className="capitalize">{p.payment_method.replace("_", " ")}</span>
                    <span>Rs {p.amount}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Line items</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Unit price</TableHead>
                <TableHead className="text-right">Tax</TableHead>
                <TableHead className="text-right">Line total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoice.items.map((it) => (
                <TableRow key={it.id}>
                  <TableCell>{it.line_number}</TableCell>
                  <TableCell>{it.product_name}</TableCell>
                  <TableCell className="font-mono text-xs">{it.product_sku}</TableCell>
                  <TableCell className="text-right font-mono">{it.quantity}</TableCell>
                  <TableCell className="text-right font-mono">Rs {it.unit_price}</TableCell>
                  <TableCell className="text-right font-mono">Rs {it.tax_amount}</TableCell>
                  <TableCell className="text-right font-mono">Rs {it.line_total}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Cancel sale</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This reverses the stock movements and marks the invoice cancelled.
              In Phase 4 the FBR rules (72-hour edit window, 10% monthly cap)
              will be enforced; for now we just keep the audit log.
            </p>
            <textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason"
              className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowConfirm(false)}>Back</Button>
              <Button
                variant="destructive"
                disabled={cancel.isPending || reason.trim().length < 2}
                onClick={async () => {
                  await cancel.mutateAsync({ id: invoice.id, reason });
                  setShowConfirm(false);
                }}
              >
                {cancel.isPending ? "Cancelling…" : "Cancel sale"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v, muted, bold }: { k: string; v: string; muted?: boolean; bold?: boolean }) {
  return (
    <div className={`flex justify-between ${muted ? "text-muted-foreground" : ""} ${bold ? "font-semibold" : ""}`}>
      <span>{k}</span>
      <span className="font-mono">{v}</span>
    </div>
  );
}

function statusVariant(status: string): "default" | "secondary" | "outline" | "destructive" {
  if (status === "valid") return "default";
  if (status === "cancelled" || status === "failed") return "destructive";
  if (status === "finalized") return "secondary";
  return "outline";
}
