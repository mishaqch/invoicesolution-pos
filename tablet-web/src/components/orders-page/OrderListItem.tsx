import { fmt, toRupees } from "@/lib/money";
import { ago } from "@/lib/utils";
import type { Invoice, OrderPayload, OrderStatus } from "@/types";

/** A held (open) order row with Resume / Void actions. */
export function HeldOrderItem({
  order,
  busy,
  onResume,
  onVoid,
}: {
  order: OrderPayload;
  busy: boolean;
  onResume: (order: OrderPayload) => void;
  onVoid: (order: OrderPayload) => void;
}) {
  const nItems = order.items.reduce((a, it) => a + Math.round(toRupees(it.quantity)), 0);
  const { label, cls } = heldStatusChip(order.order_status);
  const tableLabel = order.table || order.held_label || "Walk-in";
  const preview = order.items.map((it) => `${Math.round(toRupees(it.quantity))}× ${it.name}`).join(",  ");

  return (
    <div className="ord">
      <div className="oi">
        <div className="otop">
          <span className="otable">{tableLabel}</span>
          <span className="ono">{order.local_invoice_number ?? ""}</span>
          <span className={"ost " + cls}>{label}</span>
        </div>
        <div className="osub">
          <span>
            {nItems} item{nItems === 1 ? "" : "s"}
          </span>
          <span>·</span>
          <span>
            <b>Rs {fmt(toRupees(order.grand_total))}</b>
          </span>
          {order.kitchen_sent_at ? (
            <>
              <span>·</span>
              <span>{ago(order.kitchen_sent_at)}</span>
            </>
          ) : null}
        </div>
        {preview ? (
          <div className="osub" style={{ marginTop: 3, color: "var(--reed)" }}>
            {preview}
          </div>
        ) : null}
      </div>
      <div className="oact">
        <button type="button" className="primary" disabled={busy} onClick={() => onResume(order)}>
          Resume
        </button>
        <button type="button" className="danger" disabled={busy} onClick={() => onVoid(order)}>
          Void
        </button>
      </div>
    </div>
  );
}

/** A completed (charged) invoice row — read-only. */
export function CompletedOrderItem({ invoice }: { invoice: Invoice }) {
  const nItems = invoice.items.reduce((a, it) => a + Math.round(toRupees(it.quantity)), 0);
  // Prefer table_name; fall back to buyer_name / held_label (gaps/corrections #1).
  const label = invoice.table_name || invoice.buyer_name || invoice.held_label || "Walk-in";
  const preview = invoice.items.map((it) => `${Math.round(toRupees(it.quantity))}× ${it.product_name}`).join(",  ");

  return (
    <div className="ord">
      <div className="oi">
        <div className="otop">
          <span className="otable">{label}</span>
          <span className="ono">{invoice.local_invoice_number ?? ""}</span>
          <span className="ost done">Completed</span>
        </div>
        <div className="osub">
          <span>
            {nItems} item{nItems === 1 ? "" : "s"}
          </span>
          <span>·</span>
          <span>
            <b>Rs {fmt(toRupees(invoice.grand_total))}</b>
          </span>
          <span>·</span>
          <span>{ago(invoice.created_at)}</span>
        </div>
        {preview ? (
          <div className="osub" style={{ marginTop: 3, color: "var(--reed)" }}>
            {preview}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function heldStatusChip(status: OrderStatus): { label: string; cls: string } {
  switch (status) {
    case "sent_to_kitchen":
      return { label: "In kitchen", cls: "kitchen" };
    case "ready":
      return { label: "Ready", cls: "kitchen" };
    case "served":
      return { label: "Served", cls: "done" };
    default:
      return { label: "Saved", cls: "saved" };
  }
}
