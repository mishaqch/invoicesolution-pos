import { useRef } from "react";

import { fmt, toRupees } from "@/lib/money";
import { glyphFor, vegFor } from "@/lib/menu-glyph";
import { flyToCart } from "@/components/feedback/FlyToCart";
import { QtyStepper } from "@/components/menu/QtyStepper";
import type { PosProduct } from "@/types";

interface Props {
  product: PosProduct;
  /** Unsent quantity currently on the order for this product (0 = none). */
  qty: number;
  /** True when the product has any quantity on the order (sent or unsent) — for
   *  the .inorder highlight. */
  inOrder: boolean;
  onAdd: (product: PosProduct, source: HTMLElement) => void;
  onInc: (product: PosProduct) => void;
  onDec: (product: PosProduct) => void;
  /** Zero-based index for the entrance stagger. */
  index: number;
  /** True on a full render (category switch / search) — plays entrance. */
  animate: boolean;
}

/** A single menu dish card. Shows a "+" until on the order, then a stepper. */
export function DishCard({ product, qty, inOrder, onAdd, onInc, onDec, index, animate }: Props) {
  const addRef = useRef<HTMLButtonElement>(null);
  const veg = vegFor(product.name);
  const price = toRupees(product.sale_price);
  const hasStep = qty > 0;
  const bgA = index % 2 ? "#F3ECE0" : "#EAF1EE";
  const bgB = index % 2 ? "#E7DECB" : "#DCEBE8";

  function handleAdd(source: HTMLElement) {
    onAdd(product, source);
  }

  return (
    <div
      className={"dish" + (inOrder ? " inorder" : "")}
      data-name={product.name}
      style={animate ? { animationDelay: `${index * 40}ms` } : undefined}
      role="group"
      aria-label={product.name}
    >
      <div
        className="plate"
        style={{ background: `radial-gradient(120% 90% at 30% 10%, ${bgA}, ${bgB})` }}
      >
        <span
          className={"veg " + veg}
          role="img"
          aria-label={veg === "g" ? "Vegetarian" : "Non-vegetarian"}
          title={veg === "g" ? "Vegetarian" : "Non-vegetarian"}
        />
        <span className="food" aria-hidden="true">
          {glyphFor(product.name)}
        </span>
      </div>
      <div className="dish-body">
        <h3>{product.name}</h3>
        <p className="desc">{product.name_ur || ""}</p>
        <div className={"dish-foot" + (hasStep ? " hasstep" : "")}>
          <span className="price">
            <span className="rs">Rs</span>
            {fmt(price)}
          </span>
          {hasStep ? (
            <QtyStepper
              qty={qty}
              label={product.name}
              onInc={(e) => {
                e.stopPropagation();
                const src = (e.currentTarget as HTMLElement) ?? addRef.current;
                onInc(product);
                flyToCart(src);
              }}
              onDec={(e) => {
                e.stopPropagation();
                onDec(product);
              }}
            />
          ) : (
            <button
              ref={addRef}
              type="button"
              className="add"
              aria-label={`Add ${product.name}`}
              onClick={(e) => {
                e.stopPropagation();
                handleAdd(e.currentTarget);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
