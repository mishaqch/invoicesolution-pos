/**
 * Keyboard-wedge barcode scanner capture.
 *
 * USB/HID retail scanners present as a keyboard: they "type" the barcode's
 * characters in a rapid burst and finish with Enter. There is no device API to
 * open — we detect a scan purely by timing. Humans type at ~100–300ms between
 * keys; a scanner fires each character in well under ~30ms. So we buffer
 * keystrokes and, when Enter arrives, treat the buffer as a scan only if it was
 * entered fast enough and is long enough to be a real code.
 *
 * This means the cashier can leave focus anywhere on the sale screen (or in the
 * search box) and a scan still adds the product — the listener is window-level.
 * Genuine human typing terminated by Enter is ignored because it's too slow and
 * usually too short. Manual search still works through the search input's own
 * onChange; this hook never swallows individual characters, only acts on the
 * Enter that ends a fast burst.
 */

import { useEffect, useRef } from "react";

interface Options {
  /** Called with the scanned code once a burst terminates with Enter. */
  onScan: (code: string) => void;
  /** Disable capture (e.g. while a modal/keypad owns the keyboard). */
  enabled?: boolean;
  /** Max gap (ms) between keystrokes to still count as a single scan. */
  maxKeyGapMs?: number;
  /** Minimum buffer length to treat a burst as a barcode, not stray typing. */
  minLength?: number;
}

export function useBarcodeScanner({
  onScan,
  enabled = true,
  maxKeyGapMs = 50,
  minLength = 3,
}: Options): void {
  // Keep the latest onScan without re-binding the listener every render.
  const onScanRef = useRef(onScan);
  onScanRef.current = onScan;

  useEffect(() => {
    if (!enabled) return;

    let buffer = "";
    let lastTs = 0;

    function handler(e: KeyboardEvent) {
      // Ignore modifier-driven shortcuts (Ctrl/Alt/Meta) — never part of a scan.
      if (e.ctrlKey || e.altKey || e.metaKey) {
        buffer = "";
        return;
      }

      const now = e.timeStamp || performance.now();
      const gap = now - lastTs;
      lastTs = now;

      // A slow gap means a human is typing — start a fresh buffer from this key.
      if (gap > maxKeyGapMs) buffer = "";

      if (e.key === "Enter") {
        const code = buffer;
        buffer = "";
        // Only act on a fast, long-enough burst. Otherwise it's a human
        // pressing Enter (e.g. submitting a form) — let it through untouched.
        if (gap <= maxKeyGapMs && code.length >= minLength) {
          e.preventDefault();
          e.stopPropagation();
          onScanRef.current(code);
        }
        return;
      }

      // Accumulate only printable single characters (digits, letters, symbols
      // that appear in EAN/UPC/Code128). Multi-char keys (Shift, Tab…) reset.
      if (e.key.length === 1) {
        buffer += e.key;
        // Once we're mid-burst (chars arriving at scanner speed), suppress the
        // keystroke so the scanned digits don't also leak into the focused
        // search box. A gap > maxKeyGapMs means a human, so we never swallow
        // their typing — only the 2nd+ char of a fast burst is suppressed.
        if (buffer.length >= 2 && gap <= maxKeyGapMs) {
          e.preventDefault();
          e.stopPropagation();
        }
      } else {
        buffer = "";
      }
    }

    // Capture phase so we see the keys before an input's own handlers, letting
    // us preventDefault the terminating Enter when it's a scan.
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [enabled, maxKeyGapMs, minLength]);
}
