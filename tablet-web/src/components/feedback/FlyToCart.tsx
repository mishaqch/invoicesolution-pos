/**
 * Imperative flying-dot animation, ported 1:1 from the artifact's fly().
 * A "+" dot launches from the tapped source element and arcs into the cart
 * target (the portrait "View order" bar, or the landscape item-count chip),
 * then fades. Pure DOM — no React state, so it never causes a re-render.
 *
 * Honours prefers-reduced-motion by skipping the animation entirely.
 */
export function flyToCart(source: HTMLElement | null): void {
  if (!source) return;
  if (
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    return;
  }

  const r = source.getBoundingClientRect();
  const portrait = window.matchMedia("(max-width:820px),(orientation:portrait)").matches;
  // Land INSIDE the "View order" bar (portrait) or the item-count (landscape).
  const tgtEl = portrait
    ? document.getElementById("cartBar")
    : document.getElementById("itemCount");
  const tr = tgtEl ? tgtEl.getBoundingClientRect() : r;

  const dot = document.createElement("div");
  dot.className = "fly";
  dot.textContent = "＋";
  const dw = 24;
  const dh = 24;
  const startX = r.left + r.width / 2;
  const startY = r.top + r.height / 2;
  const endX = tr.left + tr.width / 2;
  const endY = tr.top + tr.height / 2;
  dot.style.left = `${startX - dw / 2}px`;
  dot.style.top = `${startY - dh / 2}px`;
  document.body.appendChild(dot);

  requestAnimationFrame(() => {
    dot.style.transition = "transform .6s cubic-bezier(.5,-0.3,.3,1), opacity .6s";
    dot.style.transform = `translate(${endX - startX}px, ${endY - startY}px) scale(.5)`;
    dot.style.opacity = "0";
  });
  window.setTimeout(() => dot.remove(), 640);
}
