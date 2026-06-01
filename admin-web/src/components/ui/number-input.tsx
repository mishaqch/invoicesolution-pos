/**
 * NumberInput — text field that only accepts digits (and one `.` when
 * mode="decimal"). Drop-in replacement for `<Input>` on fields like
 * prices, quantities, declared cash, card-last-4, cheque numbers.
 *
 * Why not `<input type="number">`?
 *   - On desktop browsers it still accepts "e", "E", "+", "-", and
 *     occasionally lets non-digit composition events through (IME).
 *   - Scroll/up-down arrows can silently change the value when the
 *     cashier is just scrolling the page.
 *   - Form serialization of empty type=number is inconsistent.
 *
 * What this does instead:
 *   - Keeps `type="text"` but sets the right `inputMode` so mobile
 *     phones still pop the numeric keypad.
 *   - Blocks invalid characters on `keydown` (typed input).
 *   - Sanitizes pastes via `onBeforeInput` + `onPaste` so pasting
 *     "Rs 1,234.50" yields "1234.50" (or "1234" in integer mode).
 *   - Strips a leading "0" before a non-`.` digit (so "01" becomes "1")
 *     while leaving "0.50" alone.
 *   - Calls `onChange` with the already-sanitized string. Callers
 *     never see junk in their state.
 *
 * Modes:
 *   decimal (default) — digits + at most one '.' (e.g. "12.50").
 *   integer            — digits only (e.g. "1234"). For ref numbers
 *                        (last-4-of-card, cheque #, wallet txn id, etc.)
 *
 * Negatives are never allowed.  Callers that need signed numbers
 * (stock adjustments, etc.) should use a plain Input or a future
 * SignedNumberInput rather than overload this one.
 */

import { forwardRef, useCallback, type ChangeEvent, type ClipboardEvent, type KeyboardEvent } from "react";

import { Input } from "./input";

type Mode = "decimal" | "integer";

export interface NumberInputProps {
  value: string;
  onChange: (value: string) => void;
  /** "decimal" allows one `.`; "integer" allows digits only. */
  mode?: Mode;
  /** Cap the cleaned string at this length (e.g. last-4 → 4). */
  maxLength?: number;
  /** Forwarded for accessibility / styling. */
  id?: string;
  className?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  autoFocus?: boolean;
  /** Optional aria-label for icon-only contexts. */
  "aria-label"?: string;
  /** Forwarded to <input>. Falls back to the right keypad per mode. */
  inputMode?: "decimal" | "numeric";
  /** Forwarded — handy for forms that submit on blur. */
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  /** Forwarded — for InvoiceList-style search-debounce hooks. */
  onFocus?: (e: React.FocusEvent<HTMLInputElement>) => void;
  /** Pass-through for shadcn-style aria-invalid styling. */
  "aria-invalid"?: boolean;
  name?: string;
}

/** Strip everything except digits (+ one dot in decimal mode). */
function sanitize(raw: string, mode: Mode, maxLength?: number): string {
  // Drop everything that isn't a digit or a dot.
  let cleaned = raw.replace(/[^\d.]/g, "");
  if (mode === "integer") {
    cleaned = cleaned.replace(/\./g, "");
  } else {
    // Keep at most one dot — first dot wins, additional dots are dropped.
    const firstDot = cleaned.indexOf(".");
    if (firstDot !== -1) {
      const before = cleaned.slice(0, firstDot + 1);
      const after = cleaned.slice(firstDot + 1).replace(/\./g, "");
      cleaned = before + after;
    }
  }
  // Trim leading zeros: "007" → "7", but keep "0.5" and a bare "0".
  if (cleaned.length > 1 && cleaned.startsWith("0") && cleaned[1] !== ".") {
    cleaned = cleaned.replace(/^0+/, "") || "0";
  }
  if (maxLength != null && cleaned.length > maxLength) {
    cleaned = cleaned.slice(0, maxLength);
  }
  return cleaned;
}

export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(
  function NumberInput(props, ref) {
    const {
      value,
      onChange,
      mode = "decimal",
      maxLength,
      inputMode,
      ...rest
    } = props;

    const handleChange = useCallback(
      (e: ChangeEvent<HTMLInputElement>) => {
        const clean = sanitize(e.target.value, mode, maxLength);
        if (clean !== value) onChange(clean);
      },
      [mode, maxLength, onChange, value],
    );

    const handleKeyDown = useCallback(
      (e: KeyboardEvent<HTMLInputElement>) => {
        // Allow navigation, deletion, copy/paste shortcuts.
        if (
          e.key === "Backspace" || e.key === "Delete" ||
          e.key === "ArrowLeft" || e.key === "ArrowRight" ||
          e.key === "ArrowUp" || e.key === "ArrowDown" ||
          e.key === "Home" || e.key === "End" ||
          e.key === "Tab" || e.key === "Enter" || e.key === "Escape"
        ) {
          return;
        }
        if (e.metaKey || e.ctrlKey) return; // Cmd+C / Ctrl+V etc.

        // Block "e", "E", "+", "-" — the type=number quirks. Also
        // block "." when in integer mode or when one's already there.
        if (e.key === ".") {
          if (mode === "integer" || (e.currentTarget.value || "").includes(".")) {
            e.preventDefault();
          }
          return;
        }
        if (!/^\d$/.test(e.key)) {
          e.preventDefault();
        }
      },
      [mode],
    );

    const handlePaste = useCallback(
      (e: ClipboardEvent<HTMLInputElement>) => {
        const pasted = e.clipboardData.getData("text");
        const clean = sanitize(pasted, mode, maxLength);
        if (clean !== pasted) {
          e.preventDefault();
          // React doesn't expose a native setter on the element when we
          // call element.value = clean — we have to use the prototype
          // descriptor's setter for React to register the change.
          const el = e.currentTarget;
          const proto = window.HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, "value")
            ?.set;
          setter?.call(el, clean);
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }
      },
      [mode, maxLength],
    );

    return (
      <Input
        type="text"
        // Mobile keyboards: decimal mode shows ".", integer doesn't.
        inputMode={inputMode ?? (mode === "integer" ? "numeric" : "decimal")}
        // Hint to browser autofill heuristics that this is numeric.
        pattern={mode === "integer" ? "[0-9]*" : "[0-9]*\\.?[0-9]*"}
        // Stop the browser from offering "12,345" / "$12" autofill
        // suggestions on payment fields.
        autoComplete="off"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        ref={ref}
        {...rest}
      />
    );
  },
);
