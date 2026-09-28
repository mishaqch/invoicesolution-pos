import type { FloorTable } from "@/types";

interface Props {
  table: FloorTable;
  /** True when this table is the current order's table. */
  mine: boolean;
  onSelect: (table: FloorTable) => void;
}

/** One table in the picker grid. Free / occupied / this-order states. */
export function TableTile({ table, mine, onSelect }: Props) {
  const occupied = !!table.order && !mine;
  const cls = mine ? "mine" : occupied ? "occ" : "free";
  const state = mine ? "This order" : occupied ? "Occupied" : "Free";
  const orderNo = occupied && table.order ? String(table.order.local_invoice_number ?? "") : "";

  return (
    <button
      type="button"
      className={"tbl " + cls}
      aria-label={`${table.name}, ${table.seats} seats, ${state}`}
      onClick={() => onSelect(table)}
    >
      <span className="tdot" aria-hidden="true" />
      <span className="tname">{table.name}</span>
      <span className="tseats">
        {table.seats} seats · {table.zone ?? "—"}
      </span>
      <span className="tstate">{occupied && orderNo ? `Order ${orderNo}` : state}</span>
    </button>
  );
}
