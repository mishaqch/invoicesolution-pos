import { useEffect, useState } from "react";

import IdlePromo from "./screens/IdlePromo";
import PaymentQR from "./screens/PaymentQR";
import SaleInProgress from "./screens/SaleInProgress";
import ThankYou from "./screens/ThankYou";

// Vite injects DEV; true on `npm run dev`, false on production builds.
// We also detect Electron — when the customer-display is shown by the POS
// terminal Electron process, postMessage drives state and we hide the
// devtools panel. In a regular browser tab there's no upstream sender,
// so the panel is the only way to preview each screen.
const IS_DEV = import.meta.env.DEV;
const IS_ELECTRON =
  typeof navigator !== "undefined" &&
  navigator.userAgent.toLowerCase().includes("electron");
const SHOW_DEVTOOLS = IS_DEV && !IS_ELECTRON;

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

  let screen: JSX.Element;
  switch (mode.kind) {
    case "idle":
      screen = <IdlePromo />;
      break;
    case "sale":
      screen = <SaleInProgress lines={mode.lines} total={mode.total} business={mode.business} />;
      break;
    case "qr":
      screen = <PaymentQR url={mode.url} amount={mode.amount} />;
      break;
    case "thanks":
      screen = <ThankYou />;
      break;
  }

  return (
    <>
      {screen}
      {SHOW_DEVTOOLS && <Devtools setMode={setMode} currentKind={mode.kind} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Dev-only screen switcher — visible only on `npm run dev` in a browser.
// Renders nothing in production builds and inside Electron.
// ---------------------------------------------------------------------------

function Devtools({
  setMode,
  currentKind,
}: {
  setMode: (m: Mode) => void;
  currentKind: Mode["kind"];
}) {
  const [open, setOpen] = useState(false);

  function preview(kind: Mode["kind"]) {
    switch (kind) {
      case "idle":
        setMode({ kind: "idle" });
        break;
      case "sale":
        setMode({
          kind: "sale",
          business: "Khalil General Store",
          total: "1,156.40",
          lines: [
            { name: "Atta 5kg",         qty: "1",   total: "850.00" },
            { name: "Cooking oil 1L",   qty: "2",   total: "260.00" },
            { name: "Sugar 1kg",        qty: "0.5", total: "46.40"  },
          ],
        });
        break;
      case "qr":
        setMode({
          kind: "qr",
          amount: "1,156.40",
          url: "https://easypay.example/pay?ref=DEMO-2026-0001&amount=1156.40",
        });
        break;
      case "thanks":
        setMode({ kind: "thanks" });
        break;
    }
  }

  const buttons: { kind: Mode["kind"]; label: string }[] = [
    { kind: "idle", label: "Splash / idle" },
    { kind: "sale", label: "Sale in progress" },
    { kind: "qr", label: "Payment QR" },
    { kind: "thanks", label: "Thank you" },
  ];

  return (
    <div
      style={{
        position: "fixed",
        right: 16,
        bottom: 16,
        zIndex: 9999,
        fontFamily: "system-ui, sans-serif",
        fontSize: 13,
      }}
    >
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          style={{
            background: "#0f172a",
            color: "white",
            border: "1px solid #1e293b",
            borderRadius: 8,
            padding: "8px 12px",
            boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
            cursor: "pointer",
          }}
        >
          🛠 Preview screens
        </button>
      ) : (
        <div
          style={{
            background: "rgba(15, 23, 42, 0.96)",
            color: "white",
            border: "1px solid #1e293b",
            borderRadius: 10,
            padding: 12,
            minWidth: 220,
            boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >
            <strong style={{ fontSize: 12, opacity: 0.8 }}>
              Customer-display preview
            </strong>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close devtools"
              style={{
                background: "transparent",
                color: "white",
                border: "none",
                cursor: "pointer",
                padding: 4,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>

          <div style={{ display: "grid", gap: 6 }}>
            {buttons.map((b) => {
              const active = b.kind === currentKind;
              return (
                <button
                  key={b.kind}
                  type="button"
                  onClick={() => preview(b.kind)}
                  style={{
                    background: active ? "#16a34a" : "#1e293b",
                    color: "white",
                    border: `1px solid ${active ? "#15803d" : "#334155"}`,
                    borderRadius: 6,
                    padding: "8px 10px",
                    textAlign: "left",
                    cursor: "pointer",
                    fontSize: 13,
                  }}
                >
                  {b.label}
                </button>
              );
            })}
          </div>
          <p style={{ marginTop: 10, opacity: 0.65, fontSize: 11 }}>
            Dev only. Hidden inside Electron and production builds.
          </p>
        </div>
      )}
    </div>
  );
}
