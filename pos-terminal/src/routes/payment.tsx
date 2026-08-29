import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { MethodPicker } from "@/features/payment/MethodPicker";
import { voidOpenOrder } from "@/features/restaurant/api";
import {
  BankTransferSubFlow,
  CardSubFlow,
  CashSubFlow,
  ChequeSubFlow,
  RaastSubFlow,
  SimpleReferenceSubFlow,
  StoreCreditSubFlow,
  WalletSubFlow,
} from "@/features/payment/SubFlows";
import { TenderList } from "@/features/payment/TenderList";
import { usePaymentMethods } from "@/features/payment/usePaymentMethods";
import { usePosContext } from "@/features/sale/usePosContext";
import { Money } from "@/lib/money";
import { newClientUuid } from "@/lib/uuid";
import { applyPaymentServicesRate, quoteCart, useSaleStore } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";
import { useTenderStore, type PaymentMethodCode, type Tender } from "@/stores/tender";

export default function PaymentRoute() {
  const navigate = useNavigate();
  const lines = useSaleStore((s) => s.lines);
  const cartDiscountPct = useSaleStore((s) => s.cartDiscountPct);
  const customer = useSaleStore((s) => s.customer);
  const clientUuid = useSaleStore((s) => s.clientUuid);
  const ctx = usePosContext();
  const user = useSessionStore((s) => s.user);
  const tenant = useSessionStore((s) => s.tenant);

  const tenders = useTenderStore((s) => s.tenders);
  const addTender = useTenderStore((s) => s.add);
  const removeTender = useTenderStore((s) => s.remove);
  const resetTenders = useTenderStore((s) => s.reset);
  const totalTendered = useTenderStore((s) => s.totalTendered);
  const isComplete = useTenderStore((s) => s.isComplete);

  const { config: methodConfig, error: methodConfigError } = usePaymentMethods();
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethodCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Reset tenders when entering this route fresh.
  useEffect(() => () => resetTenders(), [resetTenders]);

  if (lines.length === 0) {
    navigate("/sale", { replace: true });
    return null;
  }

  // Payment-driven services tax (PRA card rule). The reduced card rate applies
  // ONLY when the WHOLE bill is card — any cash/other tender → standard rate on
  // the whole invoice. Before any tender is added we show the standard rate so
  // the cashier sees the "pay fully by card to save" case, not a false low total.
  const CARD_METHODS = new Set<PaymentMethodCode>(["card_credit", "card_debit"]);
  const allCard = tenders.length > 0 && tenders.every((t) => CARD_METHODS.has(t.payment_method));
  // Restaurant (e.g. TDCP): the payment method sets the tax on the WHOLE bill —
  // 8% (fully card) / 16% (any other tender) on every line, regardless of HS
  // code. Other verticals keep the PRA "services chapter 98" swap.
  const isRestaurant = tenant?.vertical === "restaurant";
  const adjustedLines = applyPaymentServicesRate(lines, {
    standardRate: tenant?.services_tax_rate_standard ?? null,
    cardRate: tenant?.services_tax_rate_card ?? null,
    allCard,
    applyToAllLines: isRestaurant,
  });

  const totals = quoteCart({ lines: adjustedLines, cartDiscountPct });
  const grand = totals.grand_total;

  // Show the card-rate note when this tenant has a reduced card rate. For a
  // restaurant it applies to the whole bill (no HS-98 requirement); other
  // verticals only when a services (HS-98) line is present.
  const cardRateActive =
    !!tenant?.services_tax_rate_card &&
    (isRestaurant || lines.some((l) => (l.hs_code || "").trim().startsWith("98")));
  const tendered = totalTendered();
  const remaining = grand.sub(tendered);
  const complete = isComplete(grand);

  const storeCredit = customer
    ? Money.fromStr((customer as unknown as { store_credit?: string }).store_credit ?? "0")
    : Money.zero();

  function onAddTender(t: Omit<Tender, "id">) {
    addTender(t);
    setSelectedMethod(null); // collapse the sub-flow back to method picker
  }

  async function complete_sale() {
    if (!ctx.branch || !ctx.terminal || !ctx.session || !user) return;
    if (!complete) {
      setError("Tendered amount is less than the total.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Reuse the number already assigned when the order was saved/sent to the
      // kitchen (so the KOT, the Open-orders card and this invoice all match).
      // Only generate a fresh number for a straight-through sale that was never
      // saved/fired.
      const existingOrderNo = useSaleStore.getState().orderNumber;
      const localNumber =
        existingOrderNo ||
        (await window.api.numbering.next({
          branchCode: ctx.branch.code,
          terminalIndex: ctx.terminal.index,
        }));
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
        // FEFO batch (pharmacy) — server records the sale movement against it.
        batch_id: q.batch_id ?? null,
        // Restaurant — kept for receipt/KOT display (deltas already in price).
        modifiers: q.modifiers ?? [],
        item_note: q.item_note ?? null,
      }));

      const payments = tenders.map((t) => ({
        id: newClientUuid(),
        invoice_id: invoiceId,
        payment_method: t.payment_method,
        amount: t.amount,
        status: "completed" as const,
      }));

      const buyerRegistrationType: "Registered" | "Unregistered" = customer
        ? customer.registration_type === "registered"
          ? "Registered"
          : "Unregistered"
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
        paid_total: tendered.toStorageString(),
        change_given: remaining.isNegative() ? remaining.neg().toStorageString() : "0.0000",
        notes: null,
      };

      // Sync wire format includes the method-specific fields per tender so
      // the server-side adapter can validate + populate the right columns.
      const syncPayload = {
        client_uuid: clientUuid,
        terminal: ctx.terminal.id,
        branch: ctx.branch.id,
        cashier: user.id,
        cash_session: ctx.session.id,
        customer: customer?.id ?? null,
        local_invoice_number: localNumber,
        // Use adjustedLines (NOT the raw cart) so the server receives the
        // payment-adjusted tax rate — 8% fully-card / 16% otherwise. Sending the
        // raw lines here made the server recompute the invoice at the original
        // rate, so the card discount showed on the terminal but not on the
        // synced/final invoice. adjustedLines is a 1:1 rate-only remap of lines,
        // so every other field is identical.
        cart_lines: adjustedLines.map((l) => ({
          product: l.product_id,
          // FEFO batch (pharmacy) — server records the sale stock movement
          // against this batch. Null/absent for ordinary products.
          batch: l.batch_id ?? null,
          quantity: l.quantity,
          unit_price: l.unit_price,
          discount_pct: l.discount_pct,
          discount_amount: l.discount_amount,
          tax_rate: l.tax_rate,
          is_taxable: l.is_taxable,
          // Restaurant (empty/null for other verticals). Modifier deltas are
          // already folded into unit_price; this is the receipt + KOT snapshot.
          modifiers: l.modifiers ?? [],
          item_note: l.item_note ?? null,
          course: l.course ?? null,
        })),
        cart_discount_pct: cartDiscountPct,
        // Restaurant order-level context (null for other verticals). For a
        // restaurant sale, default the type to dine_in when the cashier never
        // picked one — matches the OrderTypeBar default and keeps the order
        // consistent. Non-restaurant verticals stay null.
        order_type:
          useSessionStore.getState().tenant?.vertical === "restaurant"
            ? (useSaleStore.getState().orderType ?? "dine_in")
            : useSaleStore.getState().orderType,
        table: useSaleStore.getState().tableId,
        covers: useSaleStore.getState().covers,
        payments: tenders.map((t) => ({
          payment_method: t.payment_method,
          amount: t.amount,
          card_last4: t.card_last4 ?? null,
          card_auth_code: t.card_auth_code ?? null,
          card_rrn: t.card_rrn ?? null,
          wallet_transaction_id: t.wallet_transaction_id ?? null,
          wallet_phone: t.wallet_phone ?? null,
          raast_transaction_id: t.raast_transaction_id ?? null,
          raast_iban: t.raast_iban ?? null,
          bank_name: t.bank_name ?? null,
          bank_account_last4: t.bank_account_last4 ?? null,
          bank_reference: t.bank_reference ?? null,
          cheque_number: t.cheque_number ?? null,
          cheque_date: t.cheque_date ?? null,
        })),
      };

      await window.api.sales.persistInvoice({
        invoice: localInvoice,
        items,
        payments,
        syncPayload,
      });

      // Drawer fires only on confirmed cash payment.
      const hasCash = tenders.some((t) => t.payment_method === "cash");
      if (hasCash) void window.api.drawer.open();

      // FBR TEST MODE (no IMS/SDC, e.g. macOS dev): stamp a dummy FBR number +
      // QR onto the local invoice BEFORE printing, so the printed receipt shows
      // the FBR logo + QR exactly like production. No-op when test mode is off
      // (the normal flow fiscalizes via SDC on the success screen instead).
      let printInvoice = localInvoice;
      try {
        if (await window.api.fiscalize.isTestMode()) {
          const r = await window.api.fiscalize.testStamp({
            invoiceId,
            localNumber,
          });
          if (r.ok && r.fbrInvoiceNumber) {
            printInvoice = { ...localInvoice, fbr_invoice_number: r.fbrInvoiceNumber };
          }
        }
      } catch {
        // Test-mode stamping is best-effort; fall back to printing without it.
      }

      const tenant = useSessionStore.getState().tenant;

      // Charge prints ONLY the customer receipt — never a kitchen slip. The KOT
      // is printed exclusively when the cashier hits "Send to kitchen"; auto-
      // firing here caused a second (kitchen) slip to print at the counter on
      // every charge, which is wrong.

      void window.api.printer.print({
        business_name: tenant?.business_name ?? "POS",
        branch_name: ctx.branch.name,
        ntn: tenant?.ntn ?? "",
        address: tenant?.address ?? undefined,
        contact: tenant?.phone ?? undefined,
        // Restaurant: order type + table on the receipt (null otherwise).
        order_type: useSaleStore.getState().orderType,
        table_name: useSaleStore.getState().tableName,
        invoice: printInvoice,
        items,
        payments,
        width: 48,
        // Non-fiscal tenants (TDCP resort) print a plain bill — no FBR QR/number
        // and no "FBR pending" notice. Fiscal is the default for everyone else.
        is_fiscal: tenant?.fbr_connection_type !== "none",
      });

      // Push the paid invoice to the server ASAP (checkout finalization).
      void window.api.sync.kick();
      void window.api?.sync?.expedite?.();

      // Restaurant: remove the order from "Open orders" IMMEDIATELY via a direct
      // call (same reliable path as Send-to-kitchen), instead of waiting for the
      // checkout invoice to sync + finalize. This guarantees a charged order
      // leaves Open orders even if the invoice sync is delayed/failing. No-op
      // (voided=false) for a straight-through sale that was never an open order.
      if (useSessionStore.getState().tenant?.vertical === "restaurant") {
        void voidOpenOrder(clientUuid).catch(() => {});
      }

      navigate("/success", {
        replace: true,
        state: {
          invoice_id: invoiceId,
          local: localNumber,
          grand: totals.grand_total.toStorageString(),
          tendered: tendered.toStorageString(),
          change: remaining.isNegative() ? remaining.neg().toStorageString() : "0.0000",
        },
      });
      useSaleStore.getState().resetForNewSale();
      resetTenders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    // h-full + min-h-0 so the payment form scrolls inside <main> when
    // a tender flow opens many sub-fields, rather than pushing the
    // header/total bar off the top of the screen.
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to cart
        </button>
        <div className="font-mono text-base">Total: Rs {grand.display()}</div>
      </header>

      <main className="mx-auto grid min-h-0 w-full max-w-4xl flex-1 grid-cols-1 gap-4 overflow-y-auto p-6 md:grid-cols-2">
        <section className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-center">
            <div className="rounded-md border bg-background p-3">
              <div className="text-xs text-muted-foreground">Tendered</div>
              <div className="font-mono text-xl">Rs {tendered.display()}</div>
            </div>
            <div
              className={`rounded-md border p-3 ${
                complete
                  ? "bg-success-soft text-success-soft-foreground"
                  : "bg-warning-soft text-warning-soft-foreground"
              }`}
            >
              <div className="text-xs">{complete ? "Done" : "Remaining"}</div>
              <div className="font-mono text-xl">
                Rs {remaining.isNegative() ? "0.00" : remaining.display()}
              </div>
            </div>
          </div>

          {cardRateActive && (
            <div
              className={`rounded-md border px-3 py-2 text-xs ${
                allCard
                  ? "border-success/40 bg-success-soft text-success-soft-foreground"
                  : "border-primary/30 bg-primary/5 text-muted-foreground"
              }`}
            >
              {allCard
                ? `Card payment — services taxed at the reduced ${Number(
                    tenant?.services_tax_rate_card,
                  )}% (card rate).`
                : `Standard ${Number(
                    tenant?.services_tax_rate_standard ?? 16,
                  )}% services rate. Pay the full bill by card to use the reduced ${Number(
                    tenant?.services_tax_rate_card,
                  )}% rate.`}
            </div>
          )}

          <TenderList tenders={tenders} onRemove={removeTender} />

          {methodConfigError && (
            <p className="rounded bg-warning-soft p-2 text-xs text-warning-soft-foreground">
              Couldn't load method config from the server. Falling back to cash only.
            </p>
          )}

          <Button
            className="w-full h-14 text-lg"
            disabled={busy || !complete || tenders.length === 0}
            onClick={complete_sale}
          >
            {busy ? "Completing…" : "Complete sale"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </section>

        <section className="space-y-4">
          {selectedMethod === null ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">Pick a payment method</p>
              {methodConfig && (
                <MethodPicker
                  enabled={methodConfig.enabled_payment_methods}
                  selected={selectedMethod}
                  onSelect={setSelectedMethod}
                />
              )}
            </div>
          ) : (
            <div className="space-y-3 rounded-md border bg-background p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium capitalize">
                  {selectedMethod.replace("_", " ")}
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedMethod(null)}
                  className="text-xs text-muted-foreground hover:underline"
                >
                  Pick another
                </button>
              </div>
              {methodConfig &&
                renderSubFlow({
                  method: selectedMethod,
                  remaining,
                  config: methodConfig,
                  hasCustomer: !!customer,
                  storeCredit,
                  onAdd: onAddTender,
                  isRestaurant,
                })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function renderSubFlow({
  method,
  remaining,
  config,
  hasCustomer,
  storeCredit,
  onAdd,
  isRestaurant,
}: {
  method: PaymentMethodCode;
  remaining: Money;
  config: import("@/features/payment/usePaymentMethods").PaymentMethodConfig;
  hasCustomer: boolean;
  storeCredit: Money;
  onAdd: (t: Omit<Tender, "id">) => void;
  isRestaurant: boolean;
}): React.ReactNode {
  const common = { remaining, config, hasCustomer, storeCredit, onAdd };
  // Restaurant (TDCP): every non-cash method uses the simplified flow — amount +
  // one OPTIONAL reference number. Cash keeps its change calculator; store credit
  // keeps its balance cap. Other verticals keep the detailed per-method forms.
  if (isRestaurant && method !== "cash" && method !== "store_credit") {
    return <SimpleReferenceSubFlow {...common} method={method} />;
  }
  switch (method) {
    case "cash":
      return <CashSubFlow {...common} />;
    case "card_credit":
      return <CardSubFlow {...common} kind="card_credit" />;
    case "card_debit":
      return <CardSubFlow {...common} kind="card_debit" />;
    case "easypaisa":
      return <WalletSubFlow {...common} kind="easypaisa" />;
    case "jazzcash":
      return <WalletSubFlow {...common} kind="jazzcash" />;
    case "raast":
      return <RaastSubFlow {...common} />;
    case "bank_transfer":
      return <BankTransferSubFlow {...common} />;
    case "store_credit":
      return <StoreCreditSubFlow {...common} />;
    case "cheque":
      return <ChequeSubFlow {...common} />;
  }
}
