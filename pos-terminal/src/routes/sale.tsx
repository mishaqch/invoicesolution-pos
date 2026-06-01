import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { CartPane } from "@/features/sale/CartPane";
import { ProductGrid } from "@/features/sale/ProductGrid";
import { TotalsPane } from "@/features/sale/TotalsPane";
import { useBarcodeScanner } from "@/features/sale/useBarcodeScanner";
import { useInitialCatalogSync } from "@/features/catalog/useInitialSync";
import { usePosContext } from "@/features/sale/usePosContext";
import { SyncStatusDot } from "@/features/sync/SyncStatusDot";
import { newClientUuid } from "@/lib/uuid";
import { terminalIndexFromName } from "@/lib/terminal";
import { quoteCart, useSaleStore } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";
import { useToast } from "@/components/feedback/Toast";

export default function SaleRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const ctx = usePosContext();
  const sync = useInitialCatalogSync();
  const user = useSessionStore((s) => s.user);
  const tenant = useSessionStore((s) => s.tenant);
  const role = useSessionStore((s) => s.role);
  const logout = useSessionStore((s) => s.logout);
  const toast = useToast();

  const addLine = useSaleStore((s) => s.addLine);
  const lines = useSaleStore((s) => s.lines);
  const setStage = useSaleStore((s) => s.setStage);
  const [scanSignal, setScanSignal] = useState(0);

  /**
   * Hardware barcode scan → add to cart. Resolves the code against the local
   * SQLite catalog (offline-capable) via an exact-barcode lookup, then adds a
   * line using the same mapping as a manual product tap. Unknown codes surface
   * a non-blocking warning so the cashier knows the scan was heard but the
   * product isn't in the catalog.
   */
  const onBarcodeScan = async (code: string) => {
    try {
      const p = await window.api.catalog.byBarcode(code);
      if (!p) {
        toast.show({
          message: t("sale.barcode_unknown", "No product for barcode {{code}}.", { code }),
          variant: "warning",
        });
        return;
      }
      addLine({
        product_id: p.id,
        product_name: p.name,
        product_sku: p.sku,
        uom_code: p.uom_code,
        hs_code: null,
        quantity: "1",
        unit_price: p.sale_price,
        discount_pct: "0",
        discount_amount: "0",
        tax_rate: p.is_taxable ? "18" : "0",
        is_taxable: !!p.is_taxable,
      });
    } catch (err) {
      console.error("Barcode lookup failed:", err);
      toast.show({
        message: t("sale.barcode_error", "Could not look up the scanned barcode."),
        variant: "destructive",
      });
    } finally {
      // Clear any stray chars the scanner leaked into the search box.
      setScanSignal((n) => n + 1);
    }
  };

  // Window-level scanner listener. Declared before any early return so the hook
  // order stays stable (rules of hooks). Only active once the catalog is usable
  // and a cash session is open.
  useBarcodeScanner({
    onScan: (code) => void onBarcodeScan(code),
    enabled: sync.status !== "syncing" && !!ctx.session,
  });

  // Gate: route to day-open if no session is open.
  if (!ctx.loading && ctx.terminal && !ctx.session) {
    navigate("/day-open", { replace: true });
    return null;
  }

  const onLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  /**
   * Hold the current cart. We persist it as a real invoice row in
   * local SQLite with `is_held=1` so the cashier can find it again
   * from the Held Sales screen. Held rows are NEVER enqueued for
   * backend sync (see electron/db/sales.ts) — they live only on the
   * terminal until the cashier recalls and completes them, at which
   * point a fresh checkout row is created and IS synced.
   *
   * Failure paths surface as non-blocking warning toasts; the cart
   * stays intact so the cashier can retry or finish charging.
   */
  async function onHold() {
    if (lines.length === 0) return;
    if (!ctx.branch || !ctx.terminal || !ctx.session || !user) {
      toast.show({
        message: t("sale.hold_no_ctx", "Cannot hold — terminal not ready."),
        variant: "warning",
      });
      return;
    }
    const label = window.prompt(
      t("sale.hold_prompt", "Hold sale — enter a label (e.g., customer name):"),
    );
    if (!label) return;
    const totals = quoteCart(useSaleStore.getState());
    const invoiceId = newClientUuid();
    try {
      const localNumber = await window.api.numbering.next({
        branchCode: ctx.branch.code,
        terminalIndex: terminalIndexFromName(ctx.terminal.name),
      });
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
      const invoiceDate = new Date().toISOString().slice(0, 10);
      await window.api.sales.persistInvoice({
        invoice: {
          id: invoiceId,
          client_uuid: useSaleStore.getState().clientUuid,
          local_invoice_number: localNumber,
          invoice_date: invoiceDate,
          customer_id: null,
          buyer_name: null,
          buyer_phone: null,
          buyer_ntn_cnic: null,
          buyer_registration_type: null,
          branch_id: ctx.branch.id,
          terminal_id: ctx.terminal.id,
          cashier_id: user.id,
          cash_session_id: ctx.session.id,
          subtotal: totals.subtotal.toStorageString(),
          discount_total: totals.discount_total.toStorageString(),
          tax_total: totals.tax_total.toStorageString(),
          grand_total: totals.grand_total.toStorageString(),
          paid_total: "0.0000",
          change_given: "0.0000",
          notes: null,
        },
        items,
        payments: [],
        is_held: true,
        held_label: label,
      });
      useSaleStore.getState().resetForNewSale();
      setStage("empty");
      toast.show({
        message: t("sale.hold_confirm", "Sale held as “{{label}}”.", { label }),
        variant: "success",
      });
    } catch (err) {
      console.error("Hold failed:", err);
      toast.show({
        message: t(
          "sale.hold_error",
          "Could not hold sale — please try again.",
        ),
        variant: "destructive",
      });
    }
  }

  if (sync.status === "syncing" && sync.productsLocal === 0) {
    return <Splash msg={t("sale.loading_catalog", "Loading catalog…")} />;
  }
  if (sync.status === "error") {
    return <Splash msg={t("sale.network_error", "Could not reach the server: {{error}}", { error: sync.error })} variant="error" />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <div className="text-xs text-muted-foreground">
          {tenant?.business_name ?? "—"} · {ctx.branch?.name ?? "—"} · {ctx.terminal?.name ?? "—"}
          {ctx.session && ctx.session.opened_with_amount && (
            <span className="ml-2">· Float Rs {ctx.session.opened_with_amount}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <SyncStatusDot />
          <button
            type="button"
            onClick={() => navigate("/today-invoices")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            {t("today_invoices.title", "Today's invoices")}
          </button>
          <button
            type="button"
            onClick={() => navigate("/held-sales")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            {t("held_sales.title")}
          </button>
          <button
            type="button"
            onClick={() => navigate("/return")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            {t("sale.return")}
          </button>
          <button
            type="button"
            onClick={() => navigate("/day-close")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            {t("day_close.title")}
          </button>
          <div className="text-right text-xs leading-tight">
            <div className="font-medium">{user?.full_name}</div>
            <div className="text-muted-foreground capitalize">{role ?? "—"}</div>
          </div>
          <button
            onClick={onLogout}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            {t("common.sign_out", "Sign out")}
          </button>
        </div>
      </header>

      {/* The grid takes the rest of the viewport. min-h-0 is critical:
          without it, a flex child can't shrink below its content's
          intrinsic height, and overflow-hidden on the inner panes
          has nothing to clip against — causing the entire right rail
          (totals) to scroll with the product list. */}
      <main className="grid min-h-0 flex-1 grid-cols-12 gap-3 overflow-hidden p-3">
        {/* Product list — the ONLY pane that scrolls. */}
        <div className="col-span-5 flex min-h-0 flex-col overflow-hidden">
          <ProductGrid onAdd={addLine} clearSignal={scanSignal} />
        </div>
        {/* Cart — own scroll if line count grows. */}
        <div className="col-span-4 flex min-h-0 flex-col overflow-hidden rounded-md border bg-background">
          <CartPane />
        </div>
        {/* Totals — pinned, never scrolls. */}
        <div className="col-span-3 flex min-h-0 flex-col overflow-hidden">
          <TotalsPane onHold={onHold} />
        </div>
      </main>
    </div>
  );
}

function Splash({
  msg,
  variant = "info",
}: {
  msg: string;
  variant?: "info" | "error";
}) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div
        className={`text-sm ${
          variant === "error" ? "text-destructive" : "text-muted-foreground"
        }`}
      >
        {msg}
      </div>
    </div>
  );
}
