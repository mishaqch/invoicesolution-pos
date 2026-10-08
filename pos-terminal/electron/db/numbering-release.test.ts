/**
 * Invoice numbers must not develop permanent holes.
 *
 * The counter advances the moment a number is REQUESTED — at fire/hold time,
 * so the kitchen slip, the open-order card and the final bill all show one
 * number. Nothing ever handed a number back, so every abandoned or voided
 * order burned one for good. On Terminal 3 in a single day that produced four
 * holes: 0908, 0914, 0919, 0934.
 *
 * releaseInvoiceNumber() rolls the counter back, but ONLY when the number
 * being released is the most recent one issued. Rolling back an earlier one
 * would re-issue a number already printed on a ticket — two different sales
 * sharing an invoice number, which is far worse than a gap.
 */

import { describe, expect, it } from "vitest";

/** Mirrors nextInvoiceNumber()/releaseInvoiceNumber() over a kv_meta map. */
function makeCounter(branchCode = "KK", terminalIndex = 3, year = 2026) {
  const meta = new Map<string, string>();
  const key = `invoice_seq:${branchCode}:T${terminalIndex}:${year}`;

  function next(): string {
    const cur = Number.parseInt(meta.get(key) ?? "0", 10);
    const n = cur + 1;
    meta.set(key, String(n));
    return `${branchCode}-T${terminalIndex}-${year}-${String(n).padStart(7, "0")}`;
  }

  function release(number: string): boolean {
    const seq = Number.parseInt(number.split("-").pop() ?? "", 10);
    if (!Number.isFinite(seq) || seq <= 0) return false;
    const cur = Number.parseInt(meta.get(key) ?? "0", 10);
    if (cur !== seq) return false;      // not the last one — leave the gap
    meta.set(key, String(seq - 1));
    return true;
  }

  return { next, release, peek: () => meta.get(key) ?? "0" };
}

describe("releasing an abandoned invoice number", () => {
  it("reuses the number when the order is voided immediately", () => {
    const c = makeCounter();
    expect(c.next()).toBe("KK-T3-2026-0000001");
    const burned = c.next();            // 0000002 — order then abandoned
    expect(burned).toBe("KK-T3-2026-0000002");

    expect(c.release(burned)).toBe(true);

    // The next real sale takes 0000002 again — no hole.
    expect(c.next()).toBe("KK-T3-2026-0000002");
  });

  it("REFUSES to roll back a number that is no longer the last", () => {
    const c = makeCounter();
    const first = c.next();             // 0000001
    c.next();                           // 0000002 — a later order took this
    expect(c.release(first)).toBe(false);
    // 0000001 is already on a printed ticket; a gap is the safe outcome.
    expect(c.peek()).toBe("2");
    expect(c.next()).toBe("KK-T3-2026-0000003");
  });

  it("never re-issues a number to two different sales", () => {
    const c = makeCounter();
    const a = c.next();
    const b = c.next();
    c.release(a);                       // refused — a is not the last
    const nextOne = c.next();
    expect(new Set([a, b, nextOne]).size).toBe(3);
  });

  it("ignores a malformed number", () => {
    const c = makeCounter();
    c.next();
    expect(c.release("not-a-number")).toBe(false);
    expect(c.release("KK-T3-2026-0000000")).toBe(false);
    expect(c.peek()).toBe("1");
  });

  it("leaves the sequence gapless across void/charge cycles", () => {
    const c = makeCounter();
    const issued: string[] = [];
    for (let i = 0; i < 5; i++) {
      const n = c.next();
      if (i % 2 === 0) issued.push(n);  // charged
      else c.release(n);                // abandoned, released immediately
    }
    expect(issued).toEqual([
      "KK-T3-2026-0000001",
      "KK-T3-2026-0000002",
      "KK-T3-2026-0000003",
    ]);
  });
});
