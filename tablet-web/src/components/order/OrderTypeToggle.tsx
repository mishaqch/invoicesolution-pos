import type { OrderType } from "@/types";

interface Props {
  value: OrderType;
  onChange: (t: OrderType) => void;
}

const OPTS: Array<{ value: OrderType; label: string }> = [
  { value: "dine_in", label: "Dine-in" },
  { value: "takeaway", label: "Takeaway" },
  { value: "delivery", label: "Delivery" },
];

/** Segmented order-type control (Dine-in / Takeaway / Delivery). */
export function OrderTypeToggle({ value, onChange }: Props) {
  return (
    <div className="otype" role="group" aria-label="Order type">
      {OPTS.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
