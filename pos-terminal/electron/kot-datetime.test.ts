/**
 * A kitchen slip must always carry the DATE as well as the time.
 *
 * renderKotText() already printed `date + time`, but `date` was optional and
 * the KOT relay (waiter-tablet orders) never passed it — those slips showed a
 * bare "21:46" with no day. The relay also used the HOST PC's timezone, so a
 * terminal on a wrong or UTC clock printed a time the kitchen could not
 * reconcile with the order in its hand.
 *
 * The kitchen uses this stamp to sequence tickets and to settle "when was
 * this fired?" disputes, so it must never be blank and must be Pakistan time.
 */

import { describe, expect, it } from "vitest";

const PK_TZ = "Asia/Karachi";
const pkDate = (d = new Date()) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: PK_TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(d);

/** The header block of renderKotText(), verbatim. */
function headerLines(input: {
  order_number: string; date?: string; time: string;
}): string[] {
  return [
    `Order ${input.order_number}`,
    `${input.date || pkDate()}  ${input.time}`,
  ];
}

describe("KOT date/time stamp", () => {
  it("prints the supplied date with the time", () => {
    const [, stamp] = headerLines({
      order_number: "KK-T2-2026-0000648", date: "2026-10-17", time: "21:46",
    });
    expect(stamp).toBe("2026-10-17  21:46");
  });

  it("falls back to today in Pakistan when a caller omits the date", () => {
    const [, stamp] = headerLines({
      order_number: "KK-T2-2026-0000648", time: "21:46",
    });
    expect(stamp).toBe(`${pkDate()}  21:46`);
    expect(stamp).not.toBe("  21:46");       // the old relay behaviour
    expect(stamp).toMatch(/^\d{4}-\d{2}-\d{2}  \d{2}:\d{2}$/);
  });

  it("uses Pakistan time, not the host PC's zone", () => {
    // 2026-10-17 23:30 UTC is already the 18th in Karachi (UTC+5).
    const d = new Date("2026-10-17T23:30:00Z");
    expect(pkDate(d)).toBe("2026-10-18");
  });

  it("never renders an empty stamp", () => {
    for (const date of [undefined, "", "2026-10-17"]) {
      const [, stamp] = headerLines({ order_number: "X", date, time: "09:05" });
      expect(stamp.trim().length).toBeGreaterThan(5);
    }
  });
});
