import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { getModifierGroups, getOpenOrder, upsertOrder, voidOrder } from "@/api/restaurant";
import { extractApiErrorMessage } from "@/lib/api";
import { buildUpsertBody, orderTotals } from "@/lib/orderPayload";
import { flyToCart } from "@/components/feedback/FlyToCart";
import { toast } from "@/components/feedback/Toast";
import { useMenu } from "@/lib/useMenu";
import { AppHeader } from "@/components/layout/AppHeader";
import { CategoryRail } from "@/components/menu/CategoryRail";
import { MenuGrid } from "@/components/menu/MenuGrid";
import { MenuHeader } from "@/components/menu/MenuHeader";
import { CartBar } from "@/components/order/CartBar";
import { OrderPanel } from "@/components/order/OrderPanel";
import { ModifierPickerSheet } from "@/components/modifiers/ModifierPickerSheet";
import { TablePickerModal } from "@/components/table/TablePickerModal";
import { useAuthStore } from "@/stores/auth";
import { useDeviceStore } from "@/stores/device";
import { useOrderStore } from "@/stores/order";
import { useUiStore } from "@/stores/ui";
import type { FloorTable, LineModifier, OpenOrdersResponse, PosProduct } from "@/types";
import { getOpenOrders } from "@/api/restaurant";

export default function OrderTakingRoute() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();

  const branchId = useDeviceStore((s) => s.branchId);
  const terminalId = useDeviceStore((s) => s.terminalId);
  const tenantName = useDeviceStore((s) => s.tenantName);
  const waiterName = useAuthStore((s) => s.userName);
  const lock = useAuthStore((s) => s.lock);

  const order = useOrderStore();
  const ui = useUiStore();

  const [busy, setBusy] = useState(false);
  const [bump, setBump] = useState(false);

  // Ensure there's always an active order draft (mints a client_uuid).
  useEffect(() => {
    if (!order.clientUuid) order.startNewOrder();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* -------------------- menu -------------------- */
  const { menu, isLoading: menuLoading, isError: menuError, error: menuErr } = useMenu();

  // Default active category to the first once the menu loads.
  useEffect(() => {
    if (!ui.activeCategory && menu.categories.length > 0) {
      ui.setActiveCategory(menu.categories[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [menu.categories]);

  const activeCat = useMemo(
    () => menu.categories.find((c) => c.id === ui.activeCategory) ?? menu.categories[0],
    [menu.categories, ui.activeCategory],
  );

  const search = ui.searchQuery.trim().toLowerCase();
  const visibleProducts = useMemo(() => {
    if (!activeCat) return [];
    const list = activeCat.products;
    if (!search) return list;
    return list.filter(
      (p) => p.name.toLowerCase().includes(search) || activeCat.name.toLowerCase().includes(search),
    );
  }, [activeCat, search]);

  /* -------------------- order derived state -------------------- */
  const unsentQtyByProduct = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of order.lines) {
      if (!l.sent_to_kitchen) m.set(l.product, (m.get(l.product) ?? 0) + l.quantity);
    }
    return m;
  }, [order.lines]);

  const inOrderIds = useMemo(() => new Set(order.lines.map((l) => l.product)), [order.lines]);

  const totalCount = order.lines.reduce((a, l) => a + l.quantity, 0);
  const newCount = order.lines.filter((l) => !l.sent_to_kitchen).reduce((a, l) => a + l.quantity, 0);
  const { subtotal, tax, grand } = orderTotals(order.lines);

  // Held-order badge count.
  const openOrdersQuery = useQuery<OpenOrdersResponse>({
    queryKey: ["open-orders", branchId, terminalId],
    queryFn: () => getOpenOrders(branchId as string, terminalId as string),
    enabled: !!branchId && !!terminalId,
  });
  const heldCount = openOrdersQuery.data?.orders.length ?? 0;

  /* -------------------- resume (from Orders page) -------------------- */
  const resumeId = params.get("resume");
  const resumingRef = useRef<string | null>(null);
  useEffect(() => {
    if (!resumeId || !terminalId || resumingRef.current === resumeId) return;
    resumingRef.current = resumeId;
    (async () => {
      setBusy(true);
      try {
        const detail = await getOpenOrder(resumeId, terminalId);
        order.rehydrateFromServer(detail);
        toast.success(`Resumed ${detail.table || detail.local_invoice_number || "order"}`);
      } catch (err) {
        toast.error(extractApiErrorMessage(err));
      } finally {
        setBusy(false);
        // Drop the ?resume= param so a reload doesn't re-resume.
        params.delete("resume");
        setParams(params, { replace: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeId, terminalId]);

  function bumpCount() {
    setBump(false);
    requestAnimationFrame(() => setBump(true));
    window.setTimeout(() => setBump(false), 420);
  }

  /* -------------------- add / inc / dec -------------------- */
  const addProduct = useCallback(
    async (product: PosProduct, source: HTMLElement) => {
      // If the product has modifier groups, open the picker; else add directly.
      try {
        const groups = await queryClient.fetchQuery({
          queryKey: ["modifier-groups", product.id],
          queryFn: () => getModifierGroups(product.id),
          staleTime: 5 * 60_000,
        });
        if (groups.length > 0) {
          ui.setModifierProductId(product.id);
          return;
        }
      } catch {
        // If the lookup fails, fall through to a plain add (waiter isn't blocked).
      }
      order.addLine(product);
      flyToCart(source);
      bumpCount();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  function confirmModifiers(product: PosProduct, modifiers: LineModifier[]) {
    order.addLine(product);
    if (modifiers.length) order.setLineModifiers(product.id, modifiers);
    ui.setModifierProductId(null);
    bumpCount();
  }

  function incProduct(product: PosProduct) {
    order.incLine(product.id);
    bumpCount();
  }
  function decProduct(product: PosProduct) {
    const ok = order.decLine(product.id);
    if (!ok) toast("Already sent to the kitchen");
  }

  const modifierProduct = useMemo(
    () =>
      ui.modifierProductId
        ? menu.categories.flatMap((c) => c.products).find((p) => p.id === ui.modifierProductId) ?? null
        : null,
    [ui.modifierProductId, menu.categories],
  );

  /* -------------------- table -------------------- */
  function selectTable(table: FloorTable) {
    // Tapping an OCCUPIED table (someone already has an order there) RESUMES that
    // order so the waiter can add a course / review it — instead of dead-ending
    // with a toast. Only when it isn't already the table in hand. Guard against
    // silently discarding a dirty unsent cart.
    if (table.order && table.id !== order.tableId) {
      const hasUnsaved = order.lines.some((l) => !l.sent_to_kitchen);
      if (hasUnsaved) {
        toast(`Finish or clear the current order before opening ${table.name}.`);
        return;
      }
      ui.setTablePickerOpen(false);
      navigate(`/?resume=${encodeURIComponent(table.order.id)}`);
      return;
    }
    order.setTable(table.id, table.name, table.seats);
    ui.setTablePickerOpen(false);
    toast.success(`Order set to ${table.name}`);
  }

  /* -------------------- save / fire / served -------------------- */
  async function persist(fire: boolean) {
    if (!branchId || !terminalId || !order.clientUuid) return;
    if (order.lines.length === 0) {
      toast("Add items first");
      return;
    }
    setBusy(true);
    try {
      const body = buildUpsertBody(
        {
          clientUuid: order.clientUuid,
          localInvoiceNumber: order.localInvoiceNumber,
          orderType: order.orderType,
          tableId: order.tableId,
          tableName: order.tableName,
          covers: order.covers,
          heldLabel: order.heldLabel,
          status: order.status,
          lines: order.lines,
        },
        { branch: branchId, terminal: terminalId, fire },
      );
      const detail = await upsertOrder(body);
      // Re-hydrate from the server response (authoritative client_uuid, status,
      // sent flags, local_invoice_number).
      order.rehydrateFromServer(detail);
      await queryClient.invalidateQueries({ queryKey: ["open-orders"] });
      await queryClient.invalidateQueries({ queryKey: ["floor"] });
      if (fire) {
        toast.success(`Sent ${newCount} item${newCount === 1 ? "" : "s"} to the kitchen 🔥`);
      } else {
        toast.success("Order saved — table held");
      }
    } catch (err) {
      toast.error(extractApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    await persist(true);
  }

  async function handleSave() {
    await persist(false);
    // Park it: start a fresh order so the waiter can serve another table.
    order.startNewOrder();
    ui.setSheetOpen(false);
  }

  async function handleServed() {
    // "Mark served" for a waiter parks/voids the working draft locally and
    // returns to a fresh order. The actual charge happens at the till; here we
    // just clear the tablet's working state.
    if (order.clientUuid) {
      try {
        await voidOrder(order.clientUuid).catch(() => undefined);
      } catch {
        /* best-effort */
      }
    }
    order.startNewOrder();
    ui.setSheetOpen(false);
    toast.success("Marked served");
  }

  /* -------------------- portrait sheet body class -------------------- */
  useEffect(() => {
    document.body.classList.toggle("sheet-open", ui.sheetOpen);
    return () => document.body.classList.remove("sheet-open");
  }, [ui.sheetOpen]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") ui.setSheetOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const orderTag =
    order.localInvoiceNumber != null
      ? String(order.localInvoiceNumber)
      : order.tableName
        ? order.tableName
        : "New order";

  function signOut() {
    lock();
    navigate("/staff", { replace: true });
  }

  return (
    <>
      <div className="app">
        <AppHeader
          tenantName={tenantName}
          tableName={order.tableName}
          covers={order.covers}
          waiterName={waiterName}
          heldCount={heldCount}
          onOpenTablePicker={() => ui.setTablePickerOpen(true)}
          onSignOut={signOut}
        />

        <CategoryRail
          categories={menu.categories}
          activeId={activeCat?.id ?? null}
          onSelect={(id) => {
            ui.setActiveCategory(id);
            document.querySelector(".menu-wrap")?.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />

        <main className="menu-wrap">
          <MenuHeader
            title={activeCat?.name ?? "Menu"}
            count={visibleProducts.length}
            search={ui.searchQuery}
            onSearch={ui.setSearchQuery}
          />
          {menuLoading ? (
            <div style={{ display: "grid", placeItems: "center", padding: 60 }}>
              <div className="page-spin" role="status" aria-label="Loading menu" />
            </div>
          ) : menuError ? (
            <div className="auth-err" role="alert" style={{ marginTop: 20 }}>
              {extractApiErrorMessage(menuErr)}
            </div>
          ) : (
            <MenuGrid
              products={visibleProducts}
              unsentQtyByProduct={unsentQtyByProduct}
              inOrderIds={inOrderIds}
              onAdd={addProduct}
              onInc={incProduct}
              onDec={decProduct}
              renderKey={`${activeCat?.id ?? ""}|${search}`}
            />
          )}
        </main>

        <OrderPanel
          status={order.status}
          orderType={order.orderType}
          onOrderType={order.setOrderType}
          heldLabel={order.heldLabel ?? ""}
          onHeldLabel={order.setHeldLabel}
          tag={orderTag}
          lines={order.lines}
          subtotal={subtotal}
          taxLabel="Service tax (16%)"
          tax={tax}
          grand={grand}
          totalCount={totalCount}
          newCount={newCount}
          busy={busy}
          bump={bump}
          onInc={(pid) => {
            order.incLine(pid);
            bumpCount();
          }}
          onDec={(pid) => {
            const ok = order.decLine(pid);
            if (!ok) toast("Already sent to the kitchen");
          }}
          onSend={handleSend}
          onSave={handleSave}
          onServed={handleServed}
          onCloseSheet={() => ui.setSheetOpen(false)}
        />
      </div>

      <CartBar
        show={order.lines.length > 0}
        itemCount={totalCount}
        total={grand}
        onOpen={() => ui.setSheetOpen(true)}
      />
      <div className="scrim" onClick={() => ui.setSheetOpen(false)} />

      {ui.tablePickerOpen && branchId ? (
        <TablePickerModal
          branchId={branchId}
          currentTableId={order.tableId}
          onSelect={selectTable}
          onClose={() => ui.setTablePickerOpen(false)}
        />
      ) : null}

      {modifierProduct ? (
        <ModifierPickerSheet
          product={modifierProduct}
          onConfirm={confirmModifiers}
          onClose={() => ui.setModifierProductId(null)}
        />
      ) : null}
    </>
  );
}
