import { ArrowLeft, Download, FileText, Pencil, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useCancelInvoice,
  useCancelInvoiceItem,
  useEditInvoiceItem,
  useInvoice,
  useResubmitInvoice,
} from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";

async function openPdf(invoiceId: string, invoiceNumber: string, download: boolean) {
  const access = useAuthStore.getState().access;
  const url = `/api/sales/invoices/${invoiceId}/pdf/${download ? "?download=1" : ""}`;
  const resp = await fetch(url, {
    headers: { ...(access ? { Authorization: `Bearer ${access}` } : {}) },
  });
  if (!resp.ok) {
    window.alert(`Failed to fetch PDF: ${resp.status}`);
    return;
  }
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  if (download) {
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `invoice-${invoiceNumber}.pdf`;
    a.click();
  } else {
    window.open(blobUrl, "_blank");
  }
  // Don't revoke immediately — Safari needs the URL alive for the new tab.
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}

function timeUntilDeadline(deadline: string | null): { remaining: string; expired: boolean } | null {
  if (!deadline) return null;
  const ms = new Date(deadline).getTime() - Date.now();
  if (ms <= 0) return { remaining: "expired", expired: true };
  const hours = Math.floor(ms / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  return { remaining: `${hours}h ${minutes}m`, expired: false };
}

export default function InvoiceDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: invoice, isLoading } = useInvoice(id);
  const cancel = useCancelInvoice();
  const cancelItem = useCancelInvoiceItem();
  const editItem = useEditInvoiceItem();
  const resubmit = useResubmitInvoice();
  const [showConfirm, setShowConfirm] = useState(false);
  const [reason, setReason] = useState("");
  const [itemPrompt, setItemPrompt] = useState<{ id: string; reason: string } | null>(null);
  const [editPrompt, setEditPrompt] = useState<{
    id: string;
    quantity: string;
    unit_price: string;
    tax_rate: string;
    reason: string;
    error?: string;
  } | null>(null);

  if (isLoading || !invoice) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }

  const deadline = timeUntilDeadline(invoice.edit_deadline_at);
  const canCancel =
    invoice.status !== "cancelled" &&
    invoice.status !== "finalized" &&
    !(deadline?.expired ?? false);
  const lockedReason = !canCancel
    ? invoice.status === "cancelled"
      ? "Already cancelled"
      : invoice.status === "finalized"
        ? "Already finalized to a return"
        : deadline?.expired
          ? "72-hour cancel window has passed (use a credit note instead)"
          : "Not eligible for cancellation"
    : null;

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
        <div className="flex items-center gap-2">
          {deadline && !deadline.expired && (
            <Badge variant="outline" className="text-amber-700"
                   title="Within this window you can edit individual line items or cancel the invoice. After it closes, you must use a credit note instead.">
              {deadline.remaining} left to amend
            </Badge>
          )}
          <Button
            variant="outline"
            onClick={() => openPdf(invoice.id, invoice.local_invoice_number, false)}
            title="Open the invoice PDF in a new tab"
          >
            <FileText className="mr-1 h-4 w-4" /> View PDF
          </Button>
          <Button
            variant="outline"
            onClick={() => openPdf(invoice.id, invoice.local_invoice_number, true)}
            title="Download the invoice PDF"
          >
            <Download className="mr-1 h-4 w-4" /> Download
          </Button>
          {(invoice.status === "failed" || invoice.status === "pending_sync")
            && !invoice.fbr_invoice_number && (
            <Button
              variant="default"
              onClick={() => void resubmit.mutateAsync(invoice.id)}
              disabled={resubmit.isPending}
              title={
                invoice.status === "failed"
                  ? "Re-queue this invoice for FBR submission"
                  : "Re-trigger sync now"
              }
            >
              <RefreshCw
                className={`mr-1 h-4 w-4 ${resubmit.isPending ? "animate-spin" : ""}`}
              />
              {resubmit.isPending ? "Resubmitting…" : "Resubmit to FBR"}
            </Button>
          )}
          {canCancel ? (
            <Button variant="destructive" onClick={() => setShowConfirm(true)}>
              Cancel sale
            </Button>
          ) : (
            <Badge variant="secondary" title={lockedReason ?? ""}>
              {lockedReason}
            </Badge>
          )}
        </div>
        {resubmit.isError && (
          <p className="ml-auto text-xs text-destructive">
            Resubmit failed: {String((resubmit.error as Error)?.message ?? "Unknown error")}
          </p>
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
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoice.items.map((it) => {
                // Edit and cancel share the same upstream "within window"
                // gate (canCancel). Edit is also blocked when the line has
                // already been edited or cancelled. Cancel is also blocked
                // when the line is already edited.
                const lineGated = it.is_cancelled || it.is_edited || !canCancel;
                return (
                  <TableRow key={it.id} className={it.is_cancelled ? "opacity-50" : ""}>
                    <TableCell>{it.line_number}</TableCell>
                    <TableCell>
                      {it.is_cancelled && <span className="mr-1 text-xs font-bold text-destructive">C</span>}
                      {it.is_edited && <span className="mr-1 text-xs font-bold text-amber-600">E</span>}
                      <span className={it.is_cancelled ? "line-through" : ""}>
                        {it.product_name}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{it.product_sku}</TableCell>
                    <TableCell className="text-right font-mono">{it.quantity}</TableCell>
                    <TableCell className="text-right font-mono">Rs {it.unit_price}</TableCell>
                    <TableCell className="text-right font-mono">Rs {it.tax_amount}</TableCell>
                    <TableCell className="text-right font-mono">Rs {it.line_total}</TableCell>
                    <TableCell className="text-right">
                      {!lineGated && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => setEditPrompt({
                              id: it.id,
                              quantity: it.quantity,
                              unit_price: it.unit_price,
                              tax_rate: it.tax_rate,
                              reason: "",
                            })}
                            className="rounded-md p-1 text-muted-foreground hover:bg-primary hover:text-primary-foreground"
                            aria-label="Edit this line"
                            title="Edit qty / price / tax (within 72h)"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setItemPrompt({ id: it.id, reason: "" })}
                            className="rounded-md p-1 text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
                            aria-label="Cancel this line"
                            title="Cancel this line"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Cancel sale</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This reverses the stock movements and marks the invoice
              cancelled. The 72-hour edit window and 10% monthly cap are
              enforced server-side; if they fail you'll see an error.
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

      {editPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Edit line item</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Patch the quantity, unit price, or tax rate. Totals
              recompute automatically. The change is sent to PRAL via
              <span className="mx-1 font-mono text-xs">editinvoice</span>
              and counts against this month's 10% amendment cap.
            </p>

            <div className="mt-4 grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="edit-qty">Quantity</Label>
                <Input
                  id="edit-qty"
                  inputMode="decimal"
                  value={editPrompt.quantity}
                  onChange={(e) => setEditPrompt({ ...editPrompt, quantity: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-price">Unit price (Rs)</Label>
                <Input
                  id="edit-price"
                  inputMode="decimal"
                  value={editPrompt.unit_price}
                  onChange={(e) => setEditPrompt({ ...editPrompt, unit_price: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-tax">Tax rate (%)</Label>
                <Input
                  id="edit-tax"
                  inputMode="decimal"
                  value={editPrompt.tax_rate}
                  onChange={(e) => setEditPrompt({ ...editPrompt, tax_rate: e.target.value })}
                />
              </div>
            </div>

            <div className="mt-3 space-y-1.5">
              <Label htmlFor="edit-reason">Reason</Label>
              <textarea
                id="edit-reason"
                rows={2}
                value={editPrompt.reason}
                onChange={(e) => setEditPrompt({ ...editPrompt, reason: e.target.value })}
                placeholder="Why is this being amended? (audit log + sent to PRAL)"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              />
            </div>

            {editPrompt.error && (
              <p className="mt-2 text-sm text-destructive">{editPrompt.error}</p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEditPrompt(null)}>
                Cancel
              </Button>
              <Button
                disabled={editItem.isPending || editPrompt.reason.trim().length < 2}
                onClick={async () => {
                  // Find the original line to figure out which fields changed.
                  const original = invoice.items.find((x) => x.id === editPrompt.id);
                  if (!original) return;
                  const patch: { quantity?: string; unit_price?: string; tax_rate?: string } = {};
                  if (editPrompt.quantity !== original.quantity) patch.quantity = editPrompt.quantity;
                  if (editPrompt.unit_price !== original.unit_price) patch.unit_price = editPrompt.unit_price;
                  if (editPrompt.tax_rate !== original.tax_rate) patch.tax_rate = editPrompt.tax_rate;
                  if (Object.keys(patch).length === 0) {
                    setEditPrompt({ ...editPrompt, error: "Nothing changed." });
                    return;
                  }
                  try {
                    await editItem.mutateAsync({
                      invoice_id: invoice.id,
                      item_id: editPrompt.id,
                      reason: editPrompt.reason,
                      ...patch,
                    });
                    setEditPrompt(null);
                  } catch (err) {
                    setEditPrompt({
                      ...editPrompt,
                      error: (err as Error).message ?? "Edit failed",
                    });
                  }
                }}
              >
                <Pencil className="mr-1 h-4 w-4" />
                {editItem.isPending ? "Saving…" : "Save edit"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {itemPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Cancel this line</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              The line is removed from the invoice total and stock for it
              is returned. Other lines stay valid; the invoice flips to
              partially cancelled.
            </p>
            <textarea
              rows={3}
              value={itemPrompt.reason}
              onChange={(e) =>
                setItemPrompt({ ...itemPrompt, reason: e.target.value })
              }
              placeholder="Reason"
              className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setItemPrompt(null)}>Back</Button>
              <Button
                variant="destructive"
                disabled={cancelItem.isPending || itemPrompt.reason.trim().length < 2}
                onClick={async () => {
                  await cancelItem.mutateAsync({
                    invoice_id: invoice.id,
                    item_id: itemPrompt.id,
                    reason: itemPrompt.reason,
                  });
                  setItemPrompt(null);
                }}
              >
                {cancelItem.isPending ? "Cancelling…" : "Cancel line"}
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
