import { useNavigate } from "react-router-dom";

import { initials } from "@/lib/utils";

interface Props {
  tenantName: string | null;
  tableName: string | null;
  covers: number;
  waiterName: string | null;
  heldCount: number;
  onOpenTablePicker: () => void;
  onSignOut: () => void;
}

/** Top bar: brand + Orders button (with held badge) + table chip + waiter. */
export function AppHeader({
  tenantName,
  tableName,
  covers,
  waiterName,
  heldCount,
  onOpenTablePicker,
  onSignOut,
}: Props) {
  const navigate = useNavigate();

  return (
    <header className="app-head">
      <div className="brand">
        <img className="mark" src="/logo-tdcp.png" alt={tenantName || "TDCP Lake Resort"} width={48} height={46} />
        <div>
          <h1>{tenantName || "TDCP Lake Resort"}</h1>
          <p>Kallar Kahar · Order Taking</p>
        </div>
      </div>
      <div className="head-spacer" />

      <button className="orders-btn" type="button" aria-label="View orders" onClick={() => navigate("/orders")}>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M8 6h13M8 12h13M8 18h13" />
          <path d="M3 6h.01M3 12h.01M3 18h.01" />
        </svg>
        <span>Orders</span>
        {heldCount > 0 ? <span className="orders-badge">{heldCount}</span> : null}
      </button>

      <button
        className="table-chip"
        type="button"
        aria-label={
          tableName
            ? `Table ${tableName}, ${covers} guests — change table`
            : "Choose a table"
        }
        onClick={onOpenTablePicker}
      >
        <span className="lbl">Table</span>
        <span className="val">{tableName ?? "No table"}</span>
        {tableName ? (
          <span className="seat" aria-hidden="true">
            {covers}
          </span>
        ) : null}
      </button>

      <div className="waiter">
        <button
          className="av"
          type="button"
          onClick={onSignOut}
          aria-label={`Signed in as ${waiterName ?? "waiter"} — tap to sign out`}
          title="Sign out"
        >
          {initials(waiterName ?? "?")}
        </button>
        <div className="who">
          <b>{waiterName ?? "Waiter"}</b>
          <span>Waiter</span>
        </div>
      </div>
    </header>
  );
}
