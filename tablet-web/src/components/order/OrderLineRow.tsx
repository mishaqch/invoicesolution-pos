import { fmt } from "@/lib/money";
import type { CartLine } from "@/types";

interface Props {
  line: CartLine;
  /** Editable = an unsent (new) line with +/- controls. */
  editable: boolean;
  /** Show a NEW tag (partially-sent product has both a sent + a new line). */
  showNewTag: boolean;
  onInc: (productId: string) => void;
  onDec: (productId: string) => void;
}

/** One row in the order panel. Editable rows get a stepper; sent rows are
 *  locked with a fixed quantity chip. Matches the artifact's .li markup. */
export function OrderLineRow({ line, editable, showNewTag, onInc, onDec }: Props) {
  const lineTotal = line.unit_price * line.quantity;

  if (editable) {
    return (
      <div className="li">
        <div className="qty">
          <button
            type="button"
            className="qbtn minus"
            aria-label={`Remove one ${line.product_name}`}
            onClick={() => onDec(line.product)}
          />
          <span className="qn">{line.quantity}</span>
          <button
            type="button"
            className="qbtn plus"
            aria-label={`Add one ${line.product_name}`}
            onClick={() => onInc(line.product)}
          />
        </div>
        <div className="nm">
          {line.product_name}
          {showNewTag ? <span className="newtag">NEW</span> : null}
          <small>Rs {fmt(line.unit_price)} each</small>
        </div>
        <div className="lp">Rs {fmt(lineTotal)}</div>
      </div>
    );
  }

  return (
    <div className="li sent">
      <div className="qfixed" title="Sent">
        {line.quantity}
      </div>
      <div className="nm">
        {line.product_name}
        <small>In kitchen · Rs {fmt(line.unit_price)} each</small>
      </div>
      <div className="lp">Rs {fmt(lineTotal)}</div>
    </div>
  );
}
