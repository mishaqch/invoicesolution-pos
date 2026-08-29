import { RefreshCw, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { buildCartLineFromProduct } from "@/features/sale/addToCart";
import { OrderTypeBar } from "@/features/restaurant/OrderTypeBar";
import { SendToKitchen } from "@/features/restaurant/SendToKitchen";
import { SaveOrder } from "@/features/restaurant/SaveOrder";
import { voidOpenOrder } from "@/features/restaurant/api";
import { voidOrderAndNotifyKitchen } from "@/features/restaurant/fire";
import {
  ModifierPicker,
  fetchModifierGroups,
  type ChosenModifiers,
} from "@/features/restaurant/ModifierPicker";
import { Money, rs } from "@/lib/money";
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
import { useTextPrompt } from "@/components/ui/TextPromptModal";

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
  const prompt = useTextPrompt();

  const addLine = useSaleStore((s) => s.addLine);
  const lines = useSaleStore((s) => s.lines);
  const setStage = useSaleStore((s) => s.setStage);
  const [scanSignal, setScanSignal] = useState(0);
  // Restaurant tenants get the order-type bar + send-to-kitchen; every other
  // vertical sees the exact current screen (no behaviour change).
  const isRestaurant = tenant?.vertical === "restaurant";

  // Void-on-empty: if the cashier resumes a saved OPEN order and then removes
  // ALL its items, an empty order is a voided order — drop it from the server
  // "Open orders" book (soft-delete) and reset to a fresh cart. Fires once:
  // resetForNewSale() clears resumedOpenOrderUuid so it won't re-trigger.
  const resumedOpenOrderUuid = useSaleStore((s) => s.resumedOpenOrderUuid);
  useEffect(() => {
    if (!isRestaurant) return;
    if (!resumedOpenOrderUuid) return;
    if (lines.length > 0) return;
    // Cart of a resumed open order just went empty → void it server-side.
    void voidOpenOrder(resumedOpenOrderUuid)
      .catch(() => {}) // best-effort; the panel also auto-refreshes
      .finally(() => {
        useSaleStore.getState().resetForNewSale();
        toast.show({ message: "Order emptied — removed from Open orders.", variant: "success" });
      });
  }, [isRestaurant, resumedOpenOrderUuid, lines.length, toast]);

  // Pending modifier-picker state: when a restaurant menu item has modifier
  // groups we hold the would-be cart line until the cashier picks options.
  const [pendingMods, setPendingMods] = useState<{
    line: Parameters<typeof addLine>[0];
    name: string;
    groups: Parameters<typeof ModifierPicker>[0]["groups"];
  } | null>(null);

  /**
   * Restaurant-aware add: if the product has modifier groups, open the picker;
   * otherwise add straight away. Non-restaurant tenants always add directly.
   */
  const addWithModifiers = async (line: Parameters<typeof addLine>[0], productId: string) => {
    if (!isRestaurant) {
      addLine(line);
      return;
    }
    const groups = await fetchModifierGroups(productId);
    if (groups.length === 0) {
      addLine(line);
      return;
    }
    setPendingMods({ line, name: line.product_name, groups });
  };

  function confirmModifiers(chosen: ChosenModifiers) {
    if (!pendingMods) return;
    const base = Money.fromStr(pendingMods.line.unit_price);
    addLine({
      ...pendingMods.line,
      unit_price: base.add(chosen.delta).toStorageString(),
      modifiers: chosen.modifiers,
    });
    setPendingMods(null);
  }

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
      // FEFO: batch-tracked products get the nearest-expiry batch attached.
      const { line, warning } = await buildCartLineFromProduct(p, {
        branchId: ctx.branch?.id ?? null,
      });
      await addWithModifiers(line, p.id);
      if (warning) {
        toast.show({ message: warning, variant: "warning" });
      }
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
    const label = await prompt({
      title: t("sale.hold_title", "Hold sale"),
      description: t("sale.hold_prompt", "Enter a label (e.g. customer name or table)."),
      placeholder: t("sale.hold_placeholder", "e.g. Ahmed / Table 5"),
      confirmLabel: t("sale.hold_confirm", "Hold"),
    });
    if (!label || !label.trim()) return;
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
        message: t("sale.hold_error", "Could not hold sale — please try again."),
        variant: "destructive",
      });
    }
  }

  /**
   * Void the current restaurant order: remove it from the server Open-orders
   * book AND, if it was already sent to the kitchen, print a CANCELLED ticket so
   * the cooks stop preparing it. Then clear the cart for the next order.
   */
  async function handleVoid() {
    const r = await voidOrderAndNotifyKitchen();
    useSaleStore.getState().resetForNewSale();
    setStage("empty");
    if (r.wasOpenOrder && r.hadFired) {
      toast.show({
        message: "Sale voided — removed from Open orders, kitchen notified to cancel.",
        variant: "success",
      });
    } else if (r.wasOpenOrder) {
      toast.show({ message: "Sale voided — removed from Open orders.", variant: "success" });
    } else if (r.hadFired) {
      toast.show({ message: "Sale voided — kitchen notified to cancel.", variant: "success" });
    } else {
      toast.show({ message: "Sale voided.", variant: "success" });
    }
  }

  if (sync.status === "syncing" && sync.productsLocal === 0) {
    return <Splash msg={t("sale.loading_catalog", "Loading catalog…")} />;
  }
  if (sync.status === "error") {
    return (
      <Splash
        msg={t("sale.network_error", "Could not reach the server: {{error}}", {
          error: sync.error,
        })}
        variant="error"
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <div className="text-xs text-muted-foreground">
          {tenant?.business_name ?? "—"} · {ctx.branch?.name ?? "—"} · {ctx.terminal?.name ?? "—"}
          {ctx.session && ctx.session.opened_with_amount && (
            <span className="ml-2">· Float Rs {rs(ctx.session.opened_with_amount)}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <SyncStatusDot />
          <button
            type="button"
            onClick={async () => {
              await sync.resync();
              toast.show({
                message: t("sale.sync_done", "Catalog synced — {{n}} products.", {
                  n: sync.productsLocal,
                }),
                variant: "success",
              });
            }}
            onContextMenu={async (e) => {
              // Right-click / long-press → "Reset catalog": wipe the local
              // products and pull a clean full set for THIS tenant. Use this if
              // the terminal is showing another tenant's products.
              e.preventDefault();
              if (
                !window.confirm(
                  "Reset catalog? This clears local products and re-downloads this account's menu.",
                )
              )
                return;
              await sync.resync(true);
              toast.show({
                message: t("sale.sync_reset", "Catalog reset — {{n}} products.", {
                  n: sync.productsLocal,
                }),
                variant: "success",
              });
            }}
            disabled={sync.status === "syncing"}
            title={
              sync.lastSyncedAt
                ? `Last synced ${new Date(sync.lastSyncedAt).toLocaleTimeString()} · ${sync.productsLocal} products · right-click to reset`
                : "Pull the latest products from the cloud (right-click to reset)"
            }
            className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-60"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${sync.status === "syncing" ? "animate-spin" : ""}`}
            />
            {sync.status === "syncing" ? t("sale.syncing", "Syncing…") : t("sale.sync", "Sync")}
          </button>
          {(tenant?.modules_enabled ?? []).includes("hotel") && (
            <button
              type="button"
              onClick={() => navigate("/stays")}
              className="rounded-md border border-primary bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              🛏 {t("stays.title", "Stays / Rooms")}
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate("/today-invoices")}
            className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            {t("today_invoices.title", "Today's invoices")}
          </button>
          {/* Restaurant parks orders in "Open orders" (via Send to kitchen),
              not the retail held-sales list — so hide this entry for them to
              avoid a confusing always-empty screen. Other verticals keep it. */}
          {!isRestaurant && (
            <button
              type="button"
              onClick={() => navigate("/held-sales")}
              className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
            >
              {t("held_sales.title")}
            </button>
          )}
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
          <button
            type="button"
            onClick={() => navigate("/hardware")}
            title={t("hardware.title", "Hardware & settings")}
            aria-label={t("hardware.title", "Hardware & settings")}
            className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
          <div className="text-right text-xs leading-tight">
            <div className="font-medium">{user?.full_name}</div>
            <div className="text-muted-foreground capitalize">{role ?? "—"}</div>
          </div>
          <button onClick={onLogout} className="rounded-md border px-2 py-1 text-xs hover:bg-muted">
            {t("common.sign_out", "Sign out")}
          </button>
        </div>
      </header>

      {isRestaurant && <OrderTypeBar branchId={ctx.branch?.id ?? null} />}

      {/* The grid takes the rest of the viewport. min-h-0 is critical:
          without it, a flex child can't shrink below its content's
          intrinsic height, and overflow-hidden on the inner panes
          has nothing to clip against — causing the entire right rail
          (totals) to scroll with the product list. */}
      <main className="grid min-h-0 flex-1 grid-cols-12 gap-3 overflow-hidden p-3">
        {/* Product list — the ONLY pane that scrolls. */}
        <div className="col-span-5 flex min-h-0 flex-col overflow-hidden">
          <ProductGrid
            onAdd={addLine}
            onAddProduct={isRestaurant ? addWithModifiers : undefined}
            branchId={ctx.branch?.id ?? null}
            onWarn={(message) => toast.show({ message, variant: "warning" })}
            clearSignal={scanSignal}
          />
        </div>
        {/* Cart — own scroll if line count grows. */}
        <div className="col-span-4 flex min-h-0 flex-col overflow-hidden rounded-md border bg-background">
          <div className="min-h-0 flex-1 overflow-hidden">
            <CartPane />
          </div>
          {isRestaurant && lines.length > 0 && (
            <div className="grid grid-cols-2 gap-2 border-t p-2">
              {/* Save order = park in Open orders WITHOUT firing the kitchen
                  (step away to another table). Send to kitchen = park AND fire
                  (KOT + KDS). Both clear the screen for the next order. */}
              <SaveOrder branchId={ctx.branch?.id ?? null} terminalId={ctx.terminal?.id ?? null} />
              <SendToKitchen
                branchId={ctx.branch?.id ?? null}
                terminalId={ctx.terminal?.id ?? null}
              />
            </div>
          )}
        </div>
        {/* Totals — pinned, never scrolls. */}
        <div className="col-span-3 flex min-h-0 flex-col overflow-hidden">
          {/* Restaurant: no generic Hold — a fired order lives in "Open orders"
              (Send to kitchen), not the retail held-sales bucket. Other
              verticals keep the classic Hold/Recall. */}
          <TotalsPane
            onHold={isRestaurant ? undefined : onHold}
            onVoid={isRestaurant ? () => void handleVoid() : undefined}
          />
        </div>
      </main>

      {pendingMods && (
        <ModifierPicker
          productName={pendingMods.name}
          groups={pendingMods.groups}
          onCancel={() => setPendingMods(null)}
          onConfirm={confirmModifiers}
        />
      )}
    </div>
  );
}

function Splash({ msg, variant = "info" }: { msg: string; variant?: "info" | "error" }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div
        className={`text-sm ${variant === "error" ? "text-destructive" : "text-muted-foreground"}`}
      >
        {msg}
      </div>
    </div>
  );
}
