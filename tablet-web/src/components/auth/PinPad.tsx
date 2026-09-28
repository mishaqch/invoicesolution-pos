import { useCallback, useEffect, useState } from "react";

interface Props {
  /** Called once 6 digits are entered (auto-submit). */
  onComplete: (pin: string) => void;
  submitting: boolean;
  /** When the parent rejects a PIN, bump this to clear the pad + shake. */
  resetSignal: number;
}

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"];
const PIN_RE = /^\d{6}$/;

/** Numeric 6-digit PIN pad with a dot indicator. Auto-submits at 6 digits;
 *  client-validates ^\d{6}$. Also accepts hardware-keyboard number input. */
export function PinPad({ onComplete, submitting, resetSignal }: Props) {
  const [pin, setPin] = useState("");

  useEffect(() => {
    setPin("");
  }, [resetSignal]);

  const submit = useCallback(
    (value: string) => {
      if (PIN_RE.test(value)) onComplete(value);
    },
    [onComplete],
  );

  const push = useCallback(
    (digit: string) => {
      setPin((prev) => {
        if (prev.length >= 6 || submitting) return prev;
        const next = prev + digit;
        if (next.length === 6) submit(next);
        return next;
      });
    },
    [submit, submitting],
  );

  const backspace = useCallback(() => {
    setPin((prev) => prev.slice(0, -1));
  }, []);

  // Hardware keyboard support (USB / Bluetooth keypads are common on tablets).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key >= "0" && e.key <= "9") {
        e.preventDefault();
        push(e.key);
      } else if (e.key === "Backspace") {
        e.preventDefault();
        backspace();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [push, backspace]);

  return (
    <div>
      <div className="pin-dots" role="status" aria-label={`${pin.length} of 6 digits entered`}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <span key={i} className={"pin-dot" + (i < pin.length ? " filled" : "")} aria-hidden="true" />
        ))}
      </div>
      <div className="pin-pad">
        {KEYS.map((k, i) => {
          if (k === "") return <span key={i} className="pin-key ghost" aria-hidden="true" />;
          if (k === "del") {
            return (
              <button
                key={i}
                type="button"
                className="pin-key"
                onClick={backspace}
                disabled={submitting || pin.length === 0}
                aria-label="Delete last digit"
              >
                ⌫
              </button>
            );
          }
          return (
            <button
              key={i}
              type="button"
              className="pin-key"
              onClick={() => push(k)}
              disabled={submitting || pin.length >= 6}
              aria-label={`Digit ${k}`}
            >
              {k}
            </button>
          );
        })}
      </div>
    </div>
  );
}
