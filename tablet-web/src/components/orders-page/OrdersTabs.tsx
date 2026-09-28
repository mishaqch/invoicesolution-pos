export type OrdersTab = "held" | "today";

interface Props {
  active: OrdersTab;
  heldCount: number;
  todayCount: number;
  onChange: (tab: OrdersTab) => void;
}

/** The Held / Today's Completed tab strip on the Orders page. */
export function OrdersTabs({ active, heldCount, todayCount, onChange }: Props) {
  return (
    <div className="zone-tabs ord-page-tabs" role="tablist" aria-label="Order lists">
      <button
        type="button"
        role="tab"
        aria-selected={active === "held"}
        onClick={() => onChange("held")}
      >
        Held / Saved <span className="tabn">{heldCount}</span>
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={active === "today"}
        onClick={() => onChange("today")}
      >
        Today's Completed <span className="tabn">{todayCount}</span>
      </button>
    </div>
  );
}
