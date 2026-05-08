import { ArrowLeft, Banknote, CreditCard, Smartphone } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { Money } from "@/lib/money";
import { newClientUuid } from "@/lib/uuid";
import { quoteCart, useSaleStore } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";
import { usePosContext } from "@/features/sale/usePosContext";

export default function PaymentRoute() {
  const navigate = useNavigate();
  const lines = useSaleStore((s) => s.lines);
  const cartDiscountPct = useSaleStore((s) => s.cartDiscountPct);
  const customer = useSaleStore((s) => s.customer);
  const clientUuid = useSaleStore((s) => s.clientUuid);
  const ctx = usePosContext();
  const user = useSessionStore((s) => s.user);

  const [tendered, setTendered] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totals = quoteCart({ lines, cartDiscountPct });
  const grand = totals.grand_total;
  const tend = tendered ? Money.fromStr(tendered) : Money.zero();
  const change = tend.sub(grand);

  if (lines.length === 0) {
    navigate("/sale", { replace: true });
    return null;
  }

  function setQuickPick(value: string) {
    setTendered(value);
  }

  async function complete() {
    if (!ctx.branch || !ctx.terminal || !ctx.session || !user) return;
    if (tend.lt(grand)) {
      setError("Tendered amount is less than the total.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = {
        branch: ctx.branch.id,
        terminal: ctx.terminal.id,
        cash_session: ctx.session.id,
        customer: customer?.id ?? null,
        cart_lines: lines.map((l) => ({
          product: l.product_id,
          quantity: l.quantity,
          unit_price: l.unit_price,
          discount_pct: l.discount_pct,
          discount_amount: l.discount_amount,
          tax_rate: l.tax_rate,
          is_taxable: l.is_taxable,
        })),
        cart_discount_pct: cartDiscountPct,
        payments: [{ payment_method: "cash", amount: tend.toStorageString() }],
        client_uuid: clientUuid,
      };

      // Server-side checkout is the source of truth: it generates the local
      // invoice number, computes totals on its end, persists in Postgres
      // (incl. stock movement, audit log). Our local mirror writes after.
      type CheckoutResp = {
        id: string;
        local_invoice_number: string;
        invoice_date: string;
        subtotal: string; discount_total: string; tax_total: string;
        grand_total: string; paid_total: string; change_given: string;
        items: { id: string; line_number: number; product: string;
                  product_name: string; product_sku: string;
                  uom_code: string; hs_code: string | null;
                  quantity: string; unit_price: string;
                  discount_pct: string; discount_amount: string;
                  tax_rate: string; tax_amount: string; line_total: string; }[];
        payments: { id: string; payment_method: string; amount: string;
                    status: string; created_at: string }[];
      };

      const invoice = await api<CheckoutResp>(
        "/sales/invoices/checkout/",
        { method: "POST", body: JSON.stringify(body) },
      );

      // Mirror to local SQLite for offline reprint + history.
      await window.api.sales.persistInvoice({
        invoice: {
          id: invoice.id,
          client_uuid: clientUuid,
          local_invoice_number: invoice.local_invoice_number,
          invoice_date: invoice.invoice_date,
          customer_id: customer?.id ?? null,
          buyer_name: customer?.name ?? null,
          buyer_phone: customer?.phone ?? null,
          buyer_ntn_cnic: customer?.ntn ?? customer?.cnic ?? null,
          buyer_registration_type: customer
            ? customer.registration_type === "registered" ? "Registered" : "Unregistered"
            : "Unregistered",
          branch_id: ctx.branch.id,
          terminal_id: ctx.terminal.id,
          cashier_id: user.id,
          cash_session_id: ctx.session.id,
          subtotal: invoice.subtotal,
          discount_total: invoice.discount_total,
          tax_total: invoice.tax_total,
          grand_total: invoice.grand_total,
          paid_total: invoice.paid_total,
          change_given: invoice.change_given,
          notes: null,
        },
        items: invoice.items.map((it) => ({
          id: it.id,
          invoice_id: invoice.id,
          line_number: it.line_number,
          product_id: it.product,
          product_name: it.product_name,
          product_sku: it.product_sku,
          uom_code: it.uom_code,
          hs_code: it.hs_code,
          quantity: it.quantity,
          unit_price: it.unit_price,
          discount_pct: it.discount_pct,
          discount_amount: it.discount_amount,
          tax_rate: it.tax_rate,
          tax_amount: it.tax_amount,
          line_total: it.line_total,
          notes: null,
        })),
        payments: invoice.payments.map((p) => ({
          id: p.id,
          invoice_id: invoice.id,
          payment_method: p.payment_method,
          amount: p.amount,
          status: p.status as "completed",
        })),
      });

      // Drawer + receipt — best-effort, never block the cashier.
      void window.api.drawer.open();
      void window.api.printer.print({
        business_name: useSessionStore.getState().tenant?.business_name ?? "POS",
        branch_name: ctx.branch.name,
        ntn: useSessionStore.getState().tenant?.ntn ?? "",
        invoice: {
          id: invoice.id,
          client_uuid: clientUuid,
          local_invoice_number: invoice.local_invoice_number,
          invoice_date: invoice.invoice_date,
          subtotal: invoice.subtotal,
          discount_total: invoice.discount_total,
          tax_total: invoice.tax_total,
          grand_total: invoice.grand_total,
          paid_total: invoice.paid_total,
          change_given: invoice.change_given,
          customer_id: null, buyer_name: null, buyer_phone: null,
          buyer_ntn_cnic: null, buyer_registration_type: null,
          branch_id: ctx.branch.id, terminal_id: ctx.terminal.id,
          cashier_id: user.id, cash_session_id: ctx.session.id,
          notes: null,
        },
        items: invoice.items,
        payments: invoice.payments,
        width: 48,
      });

      navigate("/success", {
        replace: true,
        state: {
          invoice_id: invoice.id,
          local: invoice.local_invoice_number,
          grand: invoice.grand_total,
          tendered: tend.toStorageString(),
          change: invoice.change_given,
        },
      });
      useSaleStore.getState().resetForNewSale();
    } catch (err) {
      setError(err instanceof ApiError ? `API ${err.status}` : "Checkout failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to cart
        </button>
        <div className="font-mono text-base">Total: Rs {grand.display()}</div>
      </header>

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 p-6">
        <div className="grid grid-cols-2 gap-4 text-center">
          <div className="rounded-md border bg-background p-4">
            <div className="text-xs text-muted-foreground">Tendered</div>
            <div className="mt-1 font-mono text-2xl">Rs {tend.display()}</div>
          </div>
          <div
            className={`rounded-md border p-4 ${
              change.isNegative()
                ? "bg-amber-50 text-amber-900"
                : "bg-green-50 text-green-900"
            }`}
          >
            <div className="text-xs">{change.isNegative() ? "Remaining" : "Change"}</div>
            <div className="mt-1 font-mono text-2xl">
              Rs {change.isNegative() ? change.neg().display() : change.display()}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {(["cash", "card", "easypaisa", "jazzcash", "raast", "bank"] as const).map((m) => (
            <button
              key={m}
              type="button"
              disabled={m !== "cash"}
              className={`flex h-16 flex-col items-center justify-center rounded-md border text-xs font-medium ${
                m === "cash"
                  ? "border-primary bg-primary/5"
                  : "opacity-50 cursor-not-allowed"
              }`}
              title={m !== "cash" ? "Other methods land in Phase 5" : undefined}
            >
              {m === "cash" && <Banknote className="h-5 w-5" />}
              {m === "card" && <CreditCard className="h-5 w-5" />}
              {(m === "easypaisa" || m === "jazzcash" || m === "raast") && <Smartphone className="h-5 w-5" />}
              <span className="mt-1 capitalize">{m}</span>
            </button>
          ))}
        </div>

        <div>
          <label className="text-sm font-medium">Cash tendered</label>
          <input
            type="text"
            inputMode="decimal"
            value={tendered}
            onChange={(e) => setTendered(e.target.value)}
            placeholder={grand.display()}
            className="mt-1 h-12 w-full rounded-md border bg-background px-3 font-mono text-lg outline-none focus:ring-2 focus:ring-ring"
            autoFocus
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setQuickPick(grand.toStorageString())}>
              Exact
            </Button>
            {["100", "500", "1000", "5000"].map((v) => (
              <Button key={v} variant="outline" size="sm" onClick={() => setQuickPick(v)}>
                Rs {v}
              </Button>
            ))}
          </div>
        </div>

        <Button
          size="lg"
          className="h-14 text-lg"
          disabled={busy || tend.lt(grand)}
          onClick={complete}
        >
          {busy ? "Completing…" : "Complete sale"}
        </Button>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </main>
    </div>
  );
}
