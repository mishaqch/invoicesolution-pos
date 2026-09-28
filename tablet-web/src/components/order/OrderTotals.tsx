import { fmt } from "@/lib/money";

interface Props {
  subtotal: number;
  taxLabel: string;
  tax: number;
  grand: number;
}

/**
 * Running totals for the order panel. This is a DISPLAY aid for the waiter
 * only — the authoritative, fiscalised amount is computed server-side / at the
 * till. TDCP is a non-fiscal tenant, so tax here is a shown-not-submitted PST
 * estimate.
 */
export function OrderTotals({ subtotal, taxLabel, tax, grand }: Props) {
  return (
    <div className="totals">
      <div className="trow">
        <span>Subtotal</span>
        <span>Rs {fmt(subtotal)}</span>
      </div>
      <div className="trow">
        <span>{taxLabel}</span>
        <span>Rs {fmt(tax)}</span>
      </div>
      <div className="trow grand">
        <span>Total</span>
        <span>
          <span className="rs">Rs</span> {fmt(grand)}
        </span>
      </div>
    </div>
  );
}
