import { useRef } from "react";

import type { OrderStatus } from "@/types";

interface Props {
  status: OrderStatus;
  /** Count of new (unsent) items — enables the Send button and its label. */
  newCount: number;
  /** True when any item has been sent (changes the Send label). */
  anySent: boolean;
  hasLines: boolean;
  busy: boolean;
  onSend: () => void;
  onSave: () => void;
  onServed: () => void;
}

/** Send to kitchen (with a click ripple) + Save + Mark served. */
export function OrderActions({
  status,
  newCount,
  anySent,
  hasLines,
  busy,
  onSend,
  onSave,
  onServed,
}: Props) {
  const sendRef = useRef<HTMLButtonElement>(null);

  const sendLabel =
    newCount === 0
      ? anySent
        ? "All items sent"
        : "Send to Kitchen"
      : anySent
        ? `Send ${newCount} new item${newCount === 1 ? "" : "s"}`
        : "Send to Kitchen";

  function handleSend(e: React.MouseEvent<HTMLButtonElement>) {
    if (newCount === 0 || busy) return;
    // Ripple from the click point (artifact behaviour).
    const btn = e.currentTarget;
    const r = btn.getBoundingClientRect();
    const rip = document.createElement("span");
    rip.className = "ripple";
    rip.style.left = `${e.clientX - r.left || r.width / 2}px`;
    rip.style.top = `${e.clientY - r.top || r.height / 2}px`;
    btn.appendChild(rip);
    window.setTimeout(() => rip.remove(), 600);
    onSend();
  }

  const showServed = status === "sent_to_kitchen" || status === "ready";

  return (
    <div className="actions">
      <button
        ref={sendRef}
        className="send"
        type="button"
        disabled={newCount === 0 || busy}
        onClick={handleSend}
      >
        <span aria-hidden="true">🔥</span> <span>{sendLabel}</span>
      </button>
      <div className="srow">
        <button className="btn2" type="button" onClick={onSave} disabled={!hasLines || busy}>
          Save &amp; hold table
        </button>
        {showServed ? (
          <button className="btn2 done" type="button" onClick={onServed} disabled={busy}>
            Mark served
          </button>
        ) : null}
      </div>
    </div>
  );
}
