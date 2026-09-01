import { describe, expect, it } from "vitest";

import { pkDate, pkTimeHHMM } from "./pk-time";

describe("pk-time (Asia/Karachi)", () => {
  it("formats a UTC instant as Pakistan-local time (UTC+5)", () => {
    // 2026-09-01 21:30 UTC = 2026-09-02 02:30 PKT
    const d = new Date("2026-09-01T21:30:00Z");
    expect(pkTimeHHMM(d)).toBe("02:30");
  });

  it("rolls the DATE forward for a late-UTC instant that is next-day in PKT", () => {
    // 2026-09-01 20:00 UTC = 2026-09-02 01:00 PKT → date must be the 2nd, not 1st.
    const d = new Date("2026-09-01T20:00:00Z");
    expect(pkDate(d)).toBe("2026-09-02");
  });

  it("keeps same-day date for a daytime UTC instant", () => {
    // 2026-09-01 06:00 UTC = 2026-09-01 11:00 PKT
    const d = new Date("2026-09-01T06:00:00Z");
    expect(pkDate(d)).toBe("2026-09-01");
    expect(pkTimeHHMM(d)).toBe("11:00");
  });

  it("returns YYYY-MM-DD shape", () => {
    expect(pkDate(new Date("2026-01-05T09:00:00Z"))).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
