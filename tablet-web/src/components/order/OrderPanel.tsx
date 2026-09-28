import { OrderActions } from "@/components/order/OrderActions";
import { OrderLineRow } from "@/components/order/OrderLineRow";
import { OrderTotals } from "@/components/order/OrderTotals";
import { OrderTypeToggle } from "@/components/order/OrderTypeToggle";
import { StatusChip } from "@/components/order/StatusChip";
import type { CartLine, OrderStatus, OrderType } from "@/types";

interface Props {
  status: OrderStatus;
  orderType: OrderType;
  onOrderType: (t: OrderType) => void;
  heldLabel: string;
  onHeldLabel: (label: string) => void;
  tag: string;
  lines: CartLine[];
  subtotal: number;
  taxLabel: string;
  tax: number;
  grand: number;
  totalCount: number;
  newCount: number;
  busy: boolean;
  bump: boolean;
  onInc: (productId: string) => void;
  onDec: (productId: string) => void;
  onSend: () => void;
  onSave: () => void;
  onServed: () => void;
  onCloseSheet: () => void;
}

/** The order panel (landscape column / portrait bottom-sheet). */
export function OrderPanel(props: Props) {
  const {
    status,
    orderType,
    onOrderType,
    heldLabel,
    onHeldLabel,
    tag,
    lines,
    subtotal,
    taxLabel,
    tax,
    grand,
    totalCount,
    newCount,
    busy,
    bump,
    onInc,
    onDec,
    onSend,
    onSave,
    onServed,
    onCloseSheet,
  } = props;

  const anySent = lines.some((l) => l.sent_to_kitchen);
  const newLines = lines.filter((l) => !l.sent_to_kitchen);
  const sentLines = lines.filter((l) => l.sent_to_kitchen);
  const hasLines = lines.length > 0;

  // A product is "partially sent" when it has both a sent line and a new line —
  // its new line shows a NEW tag (artifact behaviour).
  const sentProductIds = new Set(sentLines.map((l) => l.product));

  return (
    <aside className="order" aria-label="Current order">
      <div className="order-head">
        <div className="sheet-grip" aria-hidden="true" />
        <button className="sheet-close" type="button" aria-label="Close order" onClick={onCloseSheet} />
        <div className="tt">
          <h2>Current Order</h2>
          <StatusChip status={status} />
        </div>
        <p className="meta">
          Order <b>{tag}</b> ·{" "}
          <span className={"cartcount" + (bump ? " bump" : "")}>
            {totalCount} item{totalCount === 1 ? "" : "s"}
          </span>
        </p>
        <OrderTypeToggle value={orderType} onChange={onOrderType} />
        {orderType !== "dine_in" && (
          <input
            className="order-label"
            type="text"
            value={heldLabel}
            onChange={(e) => onHeldLabel(e.target.value)}
            placeholder="Guest name (e.g. Ahmed)"
            aria-label="Guest name for this order"
            maxLength={40}
          />
        )}
      </div>

      <div className="items">
        {!hasLines ? (
          <div className="empty">
            <div className="big" aria-hidden="true">
              🍽️
            </div>
            <p>Tap a dish to start building the guest's order.</p>
          </div>
        ) : (
          <>
            {newLines.length > 0 ? (
              <>
                {anySent ? <div className="grp-label">New — not sent yet</div> : null}
                {newLines.map((l) => (
                  <OrderLineRow
                    key={`new-${l.product}`}
                    line={l}
                    editable
                    showNewTag={anySent && sentProductIds.has(l.product)}
                    onInc={onInc}
                    onDec={onDec}
                  />
                ))}
              </>
            ) : null}
            {sentLines.length > 0 ? (
              <>
                <div className="grp-label">Already in kitchen</div>
                {sentLines.map((l) => (
                  <OrderLineRow
                    key={`sent-${l.product}`}
                    line={l}
                    editable={false}
                    showNewTag={false}
                    onInc={onInc}
                    onDec={onDec}
                  />
                ))}
              </>
            ) : null}
          </>
        )}
      </div>

      {hasLines ? (
        <OrderTotals subtotal={subtotal} taxLabel={taxLabel} tax={tax} grand={grand} />
      ) : null}

      <OrderActions
        status={status}
        newCount={newCount}
        anySent={anySent}
        hasLines={hasLines}
        busy={busy}
        onSend={onSend}
        onSave={onSave}
        onServed={onServed}
      />
    </aside>
  );
}
