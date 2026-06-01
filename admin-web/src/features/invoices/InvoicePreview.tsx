/**
 * Live HTML preview of an invoice draft.
 *
 * Mirrors the server-rendered A4 PDF layout closely enough that the
 * operator can sanity-check buyer name, line items, totals, and tax
 * before they commit the invoice. After save, the real
 * server-generated PDF (apps/sales/services/invoice_pdf.py) is the
 * canonical document — this is a UI aid only, never persisted.
 *
 * Designed for the right column of /sales/new. Collapses to a card on
 * narrow widths.
 */

import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTenantSetup } from "@/lib/queries";
import { useAuthStore } from "@/stores/auth";

export interface PreviewLine {
  product_name: string;
  product_sku: string;
  hs_code?: string;
  uom_code?: string;
  quantity: string;
  unit_price: string;
  discount_pct: string;
  discount_amount: string;
  tax_rate: string;
  is_taxable: boolean;
}

interface Props {
  buyer: {
    name: string | null;
    ntn: string | null;
    province: string | null;
    registrationType: "Registered" | "Unregistered";
  };
  lines: PreviewLine[];
  cartDiscountPct: string;
  invoiceType: "sale" | "debit_note" | "credit_note";
  /** What's already known about the underlying invoice — currently
   *  blank for a draft. After save the parent passes the new number
   *  and FBR id in. */
  localInvoiceNumber?: string | null;
  fbrInvoiceNumber?: string | null;
}

function n(value: string): number {
  const x = Number(value);
  return Number.isFinite(x) ? x : 0;
}

function rs(value: number): string {
  return `Rs. ${value.toLocaleString("en-PK", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

export function InvoicePreview(props: Props) {
  const tenant = useAuthStore((s) => s.tenant);
  const { data: setup } = useTenantSetup();

  // Live totals — must mirror the Live Totals card in sales/new.tsx,
  // and the backend quote+builder pipeline:
  //   1) per-line: gross - line_discount = net_before_cart_discount
  //   2) cart discount prorated across lines (each line's taxable
  //      shrinks by `cartDiscountPct`)
  //   3) tax computed on the post-cart-discount net (matches FBR's
  //      treatment of contractual discounts: tax follows taxable value)
  //   4) grand = post-cart-discount net + tax
  //
  // The earlier version of this function computed tax on the pre-
  // cart-discount net and then subtracted the cart discount from the
  // already-taxed grand — that produced a different grand than the
  // Live Totals card and the on-the-wire PRAL payload, and was wrong
  // for contractual discounts under Pakistan's Sales Tax Act.
  const totals = useMemo(() => {
    const cartPct = n(props.cartDiscountPct);
    const cartFactor = 1 - cartPct / 100;
    let subtotal = 0;
    let lineDisc = 0;
    let cartDisc = 0;
    let tax = 0;
    for (const l of props.lines) {
      const qty = n(l.quantity);
      const price = n(l.unit_price);
      const gross = qty * price;
      const pct = (gross * n(l.discount_pct)) / 100;
      const fixed = n(l.discount_amount);
      const lineDiscAmt = Math.min(gross, pct + fixed);
      const netBeforeCart = gross - lineDiscAmt;
      const net = netBeforeCart * cartFactor;
      const taxAmt = l.is_taxable ? (net * n(l.tax_rate)) / 100 : 0;
      subtotal += gross;
      lineDisc += lineDiscAmt;
      cartDisc += netBeforeCart - net;
      tax += taxAmt;
    }
    const postDiscountNet = subtotal - lineDisc - cartDisc;
    const grand = postDiscountNet + tax;
    return { subtotal, lineDisc, tax, cartDisc, grand };
  }, [props.lines, props.cartDiscountPct]);

  const typeBadge: Record<typeof props.invoiceType, { label: string; variant: "default" | "warning" | "info" }> = {
    sale: { label: "Sale invoice", variant: "default" },
    debit_note: { label: "Debit note", variant: "warning" },
    credit_note: { label: "Credit note", variant: "info" },
  };
  const bt = typeBadge[props.invoiceType];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <span>Preview</span>
          <Badge variant={bt.variant}>{bt.label}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Invoice scaffold — A4-ish proportions in a Card. */}
        <div className="rounded-md border bg-background p-4 text-[11px] leading-snug shadow-sm">
          {/* Header */}
          <div className="flex items-start justify-between border-b pb-3">
            <div>
              <div className="text-base font-semibold">
                {tenant?.business_name ?? "Your business"}
              </div>
              <div className="text-muted-foreground">
                NTN {tenant?.ntn ?? "—"}
              </div>
              {setup?.fbr_sector && (
                <div className="text-muted-foreground">
                  Sector: {setup.fbr_sector}
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="font-semibold uppercase tracking-wide text-primary">
                {bt.label}
              </div>
              <div className="text-muted-foreground">
                {props.localInvoiceNumber || "— (assigned on save)"}
              </div>
              {props.fbrInvoiceNumber && (
                <div className="text-muted-foreground">
                  FBR: {props.fbrInvoiceNumber}
                </div>
              )}
            </div>
          </div>

          {/* Buyer */}
          <div className="my-3">
            <div className="text-muted-foreground">Buyer</div>
            <div className="font-medium">{props.buyer.name || "Walk-in"}</div>
            {props.buyer.ntn && (
              <div className="text-muted-foreground">NTN/CNIC: {props.buyer.ntn}</div>
            )}
            <div className="text-muted-foreground">
              {props.buyer.registrationType}
              {props.buyer.province ? ` · ${props.buyer.province}` : ""}
            </div>
          </div>

          {/* Line items */}
          <table className="w-full border-t text-[11px]">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-1 text-left font-medium">Item</th>
                <th className="py-1 text-right font-medium">Qty</th>
                <th className="py-1 text-right font-medium">Rate</th>
                <th className="py-1 text-right font-medium">Tax</th>
                <th className="py-1 text-right font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {props.lines.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-3 text-center text-muted-foreground">
                    No lines yet
                  </td>
                </tr>
              ) : (
                props.lines.map((l, i) => {
                  const qty = n(l.quantity);
                  const price = n(l.unit_price);
                  const gross = qty * price;
                  const lineDisc = Math.min(
                    gross,
                    (gross * n(l.discount_pct)) / 100 + n(l.discount_amount),
                  );
                  const net = gross - lineDisc;
                  const taxAmt = l.is_taxable ? (net * n(l.tax_rate)) / 100 : 0;
                  const total = net + taxAmt;
                  return (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-1">
                        <div className="font-medium">{l.product_name || "(unnamed)"}</div>
                        <div className="text-muted-foreground">
                          {l.product_sku}{l.hs_code ? ` · HS ${l.hs_code}` : ""}
                        </div>
                      </td>
                      <td className="py-1 text-right font-mono">{qty}</td>
                      <td className="py-1 text-right font-mono">{rs(price)}</td>
                      <td className="py-1 text-right font-mono">
                        {l.is_taxable ? `${l.tax_rate || 0}%` : "—"}
                      </td>
                      <td className="py-1 text-right font-mono">{rs(total)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>

          {/* Totals */}
          <div className="mt-3 space-y-0.5 border-t pt-2 text-[11px]">
            <div className="flex justify-between"><span>Subtotal</span><span className="font-mono">{rs(totals.subtotal)}</span></div>
            <div className="flex justify-between text-muted-foreground"><span>Discount</span><span className="font-mono">- {rs(totals.lineDisc + totals.cartDisc)}</span></div>
            <div className="flex justify-between"><span>Tax</span><span className="font-mono">{rs(totals.tax)}</span></div>
            <div className="flex justify-between border-t pt-1 text-sm font-semibold">
              <span>Grand total</span><span className="font-mono">{rs(totals.grand)}</span>
            </div>
          </div>

          <div className="mt-3 border-t pt-2 text-[10px] text-muted-foreground">
            This is a preview. The official PDF is generated after save
            with the FBR seal + QR code.
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
