import { useEffect, useRef, useState } from "react";

import { DishCard } from "@/components/menu/DishCard";
import type { PosProduct } from "@/types";

interface Props {
  products: PosProduct[];
  /** productId -> unsent quantity on the order. */
  unsentQtyByProduct: Map<string, number>;
  /** productIds that have ANY quantity on the order (for the .inorder ring). */
  inOrderIds: Set<string>;
  onAdd: (product: PosProduct, source: HTMLElement) => void;
  onInc: (product: PosProduct) => void;
  onDec: (product: PosProduct) => void;
  /** Bumping this key triggers the entrance animation (category switch/search). */
  renderKey: string;
}

/**
 * The 4-per-row menu grid (auto-fill, minmax(158px,1fr)). The entrance
 * animation plays ONLY on a full render (category switch / search), never on an
 * in-place quantity change — matching the artifact's `.grid.animate` toggle.
 */
export function MenuGrid({
  products,
  unsentQtyByProduct,
  inOrderIds,
  onAdd,
  onInc,
  onDec,
  renderKey,
}: Props) {
  const [animate, setAnimate] = useState(true);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    setAnimate(true);
    window.clearTimeout(timer.current);
    // Drop the animate flag once the entrance has run so later reflows (a
    // quantity change) don't replay it.
    timer.current = window.setTimeout(() => setAnimate(false), 700);
    return () => window.clearTimeout(timer.current);
  }, [renderKey]);

  return (
    <div className={"grid" + (animate ? " animate" : "")}>
      {products.map((p, i) => (
        <DishCard
          key={p.id}
          product={p}
          qty={unsentQtyByProduct.get(p.id) ?? 0}
          inOrder={inOrderIds.has(p.id)}
          onAdd={onAdd}
          onInc={onInc}
          onDec={onDec}
          index={i}
          animate={animate}
        />
      ))}
    </div>
  );
}
