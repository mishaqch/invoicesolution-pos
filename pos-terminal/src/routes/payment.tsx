import { ArrowLeft, Banknote, CreditCard, Smartphone } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Money } from "@/lib/money";
import { newClientUuid } from "@/lib/uuid";
import { quoteCart, useSaleStore } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";
import { usePosContext } from "@/features/sale/usePosContext";

function terminalIndexFromName(name: string): number {
  const digits = name.match(/\d+/);
  return digits ? parseInt(digits[0], 10) : 1;
}

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
      // Phase 3 inversion: the cashier never blocks on the network.
      //   1. Generate local_invoice_number + invoice id locally.
      //   2. Persist invoice + items + payments + outbound_queue row in
      //      a single SQLite transaction.
      //   3. Return success to the cashier (drawer + receipt fire here).
      //   4. The sync worker drains outbound_queue in the background.
      const localNumber = await window.api.numbering.next({
        branchCode: ctx.branch.code,
        terminalIndex: terminalIndexFromName(ctx.terminal.name),
      });
      const invoiceId = newClientUuid();
      const invoiceDate = new Date().toISOString().slice(0, 10);

      const items = totals.lines.map((q, i) => ({
        id: newClientUuid(),
        invoice_id: invoiceId,
        line_number: i + 1,
        product_id: q.product_id,
        product_name: q.product_name,
        product_sku: q.product_sku,
        uom_code: q.uom_code,
        hs_code: q.hs_code,
        quantity: q.quantity,
        unit_price: q.unit_price,
        discount_pct: q.discount_pct,
        discount_amount: q.discount_amount,
        tax_rate: q.tax_rate,
        tax_amount: q.tax_amount.toStorageString(),
        line_total: q.line_total.toStorageString(),
        notes: null,
      }));

      const payments = [{
        id: newClientUuid(),
        invoice_id: invoiceId,
        payment_method: "cash" as const,
        amount: tend.toStorageString(),
        status: "completed" as const,
      }];

      const buyerRegistrationType: "Registered" | "Unregistered" = customer
        ? customer.registration_type === "registered" ? "Registered" : "Unregistered"
        : "Unregistered";

      const localInvoice = {
        id: invoiceId,
        client_uuid: clientUuid,
        local_invoice_number: localNumber,
        invoice_date: invoiceDate,
        customer_id: customer?.id ?? null,
        buyer_name: customer?.name ?? null,
        buyer_phone: customer?.phone ?? null,
        buyer_ntn_cnic: customer?.ntn ?? customer?.cnic ?? null,
        buyer_registration_type: buyerRegistrationType,
        branch_id: ctx.branch.id,
        terminal_id: ctx.terminal.id,
        cashier_id: user.id,
        cash_session_id: ctx.session.id,
        subtotal: totals.subtotal.toStorageString(),
        discount_total: totals.discount_total.toStorageString(),
        tax_total: totals.tax_total.toStorageString(),
        grand_total: totals.grand_total.toStorageString(),
        paid_total: tend.toStorageString(),
        change_given: change.isPositive() ? change.toStorageString() : "0.0000",
        notes: null,
      };

      // Sync wire format (matches IngestInvoiceSerializer on the server).
      const syncPayload = {
        client_uuid: clientUuid,
        terminal: ctx.terminal.id,
        branch: ctx.branch.id,
        cashier: user.id,
        cash_session: ctx.session.id,
        customer: customer?.id ?? null,
        local_invoice_number: localNumber,
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
        payments: payments.map((p) => ({
          payment_method: p.payment_method, amount: p.amount,
        })),
      };

      await window.api.sales.persistInvoice({
        invoice: localInvoice,
        items,
        payments,
        syncPayload,
      });

      // Best-effort drawer + receipt — never block the cashier.
      void window.api.drawer.open();
      void window.api.printer.print({
        business_name: useSessionStore.getState().tenant?.business_name ?? "POS",
        branch_name: ctx.branch.name,
        ntn: useSessionStore.getState().tenant?.ntn ?? "",
        invoice: localInvoice,
        items,
        payments,
        width: 48,
      });

      // Kick the worker so it drains immediately.
      void window.api.sync.kick();

      navigate("/success", {
        replace: true,
        state: {
          invoice_id: invoiceId,
          local: localNumber,
          grand: totals.grand_total.toStorageString(),
          tendered: tend.toStorageString(),
          change: change.isPositive() ? change.toStorageString() : "0.0000",
        },
      });
      useSaleStore.getState().resetForNewSale();
    } catch (err) {
      // Local-first means this branch is rare: only fires if SQLite
      // itself errored or numbering failed. Both are programmer bugs.
      setError(err instanceof Error ? err.message : "Checkout failed.");
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
