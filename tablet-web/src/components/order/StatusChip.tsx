import type { OrderStatus } from "@/types";

const LABEL: Record<OrderStatus, string> = {
  open: "Open",
  sent_to_kitchen: "Sent to kitchen",
  ready: "Ready to serve",
  served: "Served",
};

const CLS: Record<OrderStatus, string> = {
  open: "s-open",
  sent_to_kitchen: "s-sent",
  ready: "s-ready",
  served: "s-ready",
};

/** Order status pill (open / sent / ready / served). */
export function StatusChip({ status }: { status: OrderStatus }) {
  return (
    <span className={`status ${CLS[status]}`}>
      <span className="dot" aria-hidden="true" /> {LABEL[status]}
    </span>
  );
}
