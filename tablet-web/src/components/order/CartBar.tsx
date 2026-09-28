import { fmt } from "@/lib/money";

interface Props {
  show: boolean;
  itemCount: number;
  total: number;
  onOpen: () => void;
}

/** Portrait-only floating cart bar. `id="cartBar"` is the flying-dot target. */
export function CartBar({ show, itemCount, total, onOpen }: Props) {
  return (
    <button
      id="cartBar"
      className={"cart-bar" + (show ? " show" : "")}
      type="button"
      aria-label="Open current order"
      onClick={onOpen}
    >
      <div className="cb-info">
        <b>Rs {fmt(total)}</b>
        <span>
          {itemCount} item{itemCount === 1 ? "" : "s"}
        </span>
      </div>
      <div className="cb-cta">
        <svg
          width="17"
          height="17"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="9" cy="21" r="1" />
          <circle cx="20" cy="21" r="1" />
          <path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6" />
        </svg>
        View order
      </div>
    </button>
  );
}
