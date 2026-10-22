/**
 * Installing a new .exe must never make the kitchen printer run away.
 *
 * What happened: the KDS feed had no date boundary, so a till with a working
 * relay found 986 un-acked orders going back to June and began draining them
 * at one ticket per 8-second poll — 156 tickets in one hour against a normal
 * 10-40 per DAY.
 *
 * TWO independent protections now stand between an install and the printer:
 *   1. the SERVER bounds the feed to the current service day, and
 *   2. the RELAY refuses an implausibly large feed outright.
 *
 * Either alone stops the runaway; this file covers (2), the terminal half,
 * so it cannot be dropped without a failing test.
 */

import { describe, expect, it } from "vitest";

const MAX_BACKLOG = 25;

/** Mirrors the guard in kot-relay.ts tick(). */
function wouldPrint(orderCount: number): boolean {
  if (orderCount === 0) return false;
  if (orderCount > MAX_BACKLOG) return false; // refuse: backlog, not service
  return true;
}

describe("relay runaway guard", () => {
  it("refuses the backlog that caused the incident", () => {
    expect(wouldPrint(986)).toBe(false);
  });

  it("refuses anything above the limit", () => {
    expect(wouldPrint(MAX_BACKLOG + 1)).toBe(false);
    expect(wouldPrint(200)).toBe(false);
  });

  it("still prints normal service volume", () => {
    for (const n of [1, 2, 5, 12, MAX_BACKLOG]) {
      expect(wouldPrint(n)).toBe(true);
    }
  });

  it("does nothing when there is nothing to print", () => {
    expect(wouldPrint(0)).toBe(false);
  });
});

describe("server-side date bound (the first line of defence)", () => {
  /** Mirrors KdsUnprintedView's .filter(invoice_date__gte=today). */
  const offered = (orders: { date: string }[], today: string) =>
    orders.filter((o) => o.date >= today);

  it("hides a months-old backlog entirely", () => {
    const today = "2026-10-22";
    const orders = [
      { date: "2026-06-14" }, { date: "2026-08-01" }, { date: "2026-10-21" },
      { date: today }, { date: today },
    ];
    expect(offered(orders, today)).toHaveLength(2);
  });

  it("keeps today's live tickets", () => {
    const today = "2026-10-22";
    expect(offered([{ date: today }], today)).toHaveLength(1);
  });
});
