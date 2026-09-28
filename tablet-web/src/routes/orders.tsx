import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { getOpenOrders, voidOrder } from "@/api/restaurant";
import { getTodayCompletedOrders } from "@/api/sales";
import { extractApiErrorMessage } from "@/lib/api";
import { toast } from "@/components/feedback/Toast";
import { OrdersTabs, type OrdersTab } from "@/components/orders-page/OrdersTabs";
import { CompletedOrderItem, HeldOrderItem } from "@/components/orders-page/OrderListItem";
import { useDeviceStore } from "@/stores/device";
import type { InvoiceListResponse, OpenOrdersResponse, OrderPayload } from "@/types";

/** /orders — full page with Held/Saved + Today's Completed tabs. Back = -1. */
export default function OrdersRoute() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const branchId = useDeviceStore((s) => s.branchId);
  const terminalId = useDeviceStore((s) => s.terminalId);

  const [tab, setTab] = useState<OrdersTab>("held");
  const [voiding, setVoiding] = useState<string | null>(null);

  const heldQuery = useQuery<OpenOrdersResponse>({
    queryKey: ["open-orders", branchId, terminalId],
    queryFn: () => getOpenOrders(branchId as string, terminalId as string),
    enabled: !!branchId && !!terminalId,
  });

  // Completed = today's charged invoices, filtered by BRANCH ONLY (never
  // terminal — charging happens at the till, a different terminal).
  const completedQuery = useQuery<InvoiceListResponse>({
    queryKey: ["today-completed", branchId],
    queryFn: () => getTodayCompletedOrders(branchId as string),
    enabled: !!branchId && tab === "today",
  });

  const held = heldQuery.data?.orders ?? [];
  const completed = completedQuery.data?.results ?? [];

  function resume(order: OrderPayload) {
    // Hand the invoice id to the order-taking screen, which fetches the detail
    // and rehydrates the draft (client_uuid taken from the server).
    navigate(`/?resume=${encodeURIComponent(order.id)}`);
  }

  async function handleVoid(order: OrderPayload) {
    // The open-order list payload doesn't carry client_uuid; resolve it from the
    // detail before voiding. Simpler: the void endpoint keys on client_uuid, and
    // the detail fetch gives it to us — but to avoid an extra round-trip we void
    // via the order detail's client_uuid loaded lazily here.
    setVoiding(order.id);
    try {
      const { getOpenOrder } = await import("@/api/restaurant");
      const detail = await getOpenOrder(order.id, terminalId as string);
      const res = await voidOrder(detail.client_uuid);
      if (res.voided) {
        toast.success(`Voided ${order.local_invoice_number ?? "order"}`);
      } else {
        toast(`Nothing to void`);
      }
      await queryClient.invalidateQueries({ queryKey: ["open-orders"] });
      await queryClient.invalidateQueries({ queryKey: ["floor"] });
    } catch (err) {
      toast.error(extractApiErrorMessage(err));
    } finally {
      setVoiding(null);
    }
  }

  return (
    <section className="ord-page" aria-labelledby="ord-title">
      <header className="ord-page-head">
        <button className="ord-back" type="button" aria-label="Back" onClick={() => navigate(-1)}>
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <div className="ord-htxt">
          <h1 id="ord-title">Orders</h1>
          <p>Resume a held order, or review what's been served today · synced with the POS</p>
        </div>
      </header>

      <OrdersTabs active={tab} heldCount={held.length} todayCount={completed.length} onChange={setTab} />

      <div className="orders-list">
        {tab === "held" ? (
          heldQuery.isLoading ? (
            <Spinner label="Loading held orders" />
          ) : heldQuery.isError ? (
            <ErrorBox message={extractApiErrorMessage(heldQuery.error)} />
          ) : held.length === 0 ? (
            <EmptyState
              icon="📋"
              text="No held or saved orders right now. Save an order to park it here."
            />
          ) : (
            held.map((o) => (
              <HeldOrderItem
                key={o.id}
                order={o}
                busy={voiding === o.id}
                onResume={resume}
                onVoid={handleVoid}
              />
            ))
          )
        ) : completedQuery.isLoading ? (
          <Spinner label="Loading completed orders" />
        ) : completedQuery.isError ? (
          <ErrorBox message={extractApiErrorMessage(completedQuery.error)} />
        ) : completed.length === 0 ? (
          <EmptyState icon="✅" text="No completed orders yet today." />
        ) : (
          completed.map((inv) => <CompletedOrderItem key={inv.id} invoice={inv} />)
        )}
      </div>
    </section>
  );
}

function Spinner({ label }: { label: string }) {
  return (
    <div style={{ display: "grid", placeItems: "center", padding: 40 }}>
      <div className="page-spin" role="status" aria-label={label} />
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="auth-err" role="alert">
      {message}
    </div>
  );
}

function EmptyState({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="ord-empty">
      <div className="big" aria-hidden="true">
        {icon}
      </div>
      <p>{text}</p>
    </div>
  );
}
