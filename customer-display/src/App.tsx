import { useEffect, useState } from "react";

import IdlePromo from "./screens/IdlePromo";
import SaleInProgress from "./screens/SaleInProgress";
import ThankYou from "./screens/ThankYou";
import PaymentQR from "./screens/PaymentQR";

/**
 * Customer-facing display. Listens for postMessage events from the POS
 * terminal Electron process to switch between four states:
 *
 *   { type: "idle" }
 *   { type: "sale", lines, total, business }
 *   { type: "qr", url, amount }
 *   { type: "thanks" }
 *
 * Idle state rotates through promo slides on a 6s interval.
 */

type Mode =
  | { kind: "idle" }
  | { kind: "sale"; lines: SaleLine[]; total: string; business: string }
  | { kind: "qr"; url: string; amount: string }
  | { kind: "thanks" };

interface SaleLine {
  name: string;
  qty: string;
  total: string;
}

export default function App() {
  const [mode, setMode] = useState<Mode>({ kind: "idle" });

  useEffect(() => {
    function handler(ev: MessageEvent) {
      const msg = ev.data;
      if (!msg || typeof msg !== "object") return;
      switch (msg.type) {
        case "idle":
          setMode({ kind: "idle" });
          break;
        case "sale":
          setMode({
            kind: "sale",
            lines: msg.lines ?? [],
            total: String(msg.total ?? "0"),
            business: String(msg.business ?? ""),
          });
          break;
        case "qr":
          setMode({
            kind: "qr",
            url: String(msg.url ?? ""),
            amount: String(msg.amount ?? "0"),
          });
          break;
        case "thanks":
          setMode({ kind: "thanks" });
          // Auto-return to idle after 4s.
          window.setTimeout(() => setMode({ kind: "idle" }), 4000);
          break;
      }
    }
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  switch (mode.kind) {
    case "idle":
      return <IdlePromo />;
    case "sale":
      return <SaleInProgress lines={mode.lines} total={mode.total} business={mode.business} />;
    case "qr":
      return <PaymentQR url={mode.url} amount={mode.amount} />;
    case "thanks":
      return <ThankYou />;
  }
}
