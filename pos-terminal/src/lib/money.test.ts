import { describe, expect, it } from "vitest";

import { Money, sumMoney } from "./money";

describe("Money", () => {
  it("zero", () => {
    expect(Money.zero().toStorageString()).toBe("0.0000");
  });

  it("from_str round-trips", () => {
    expect(Money.fromStr("1").toStorageString()).toBe("1.0000");
    expect(Money.fromStr("1.5").toStorageString()).toBe("1.5000");
    expect(Money.fromStr("0.01").toStorageString()).toBe("0.0100");
  });

  it("from_str rounds half-up beyond 4dp", () => {
    expect(Money.fromStr("1.23456").toStorageString()).toBe("1.2346");
  });

  it("addition is exact", () => {
    let total = Money.zero();
    for (let i = 0; i < 100; i++) {
      total = total.add(Money.fromStr("0.01"));
    }
    expect(total.toStorageString()).toBe("1.0000");
    expect(total.display()).toBe("1.00");
  });

  it("Rs 1000 × 18% === 180.00 exactly", () => {
    const tax = Money.fromStr("1000").applyPct(18);
    expect(tax.toStorageString()).toBe("180.0000");
    expect(tax.display()).toBe("180.00");
  });

  it("Rs 240 × 1.5 kg === 360.00", () => {
    expect(Money.fromStr("240").mulScalar("1.5").toStorageString()).toBe("360.0000");
  });

  it("paisa round-trip", () => {
    // 12345 paisa = Rs 123.45
    expect(Money.fromPaisa(12345).display()).toBe("123.45");
  });

  it("display rounds half-up", () => {
    expect(Money.fromStr("1.235").display()).toBe("1.24");
    expect(Money.fromStr("1.234").display()).toBe("1.23");
  });

  it("subtraction can go negative", () => {
    expect(Money.fromStr("5").sub(Money.fromStr("12")).toStorageString()).toBe("-7.0000");
    expect(Money.fromStr("5").sub(Money.fromStr("12")).display()).toBe("-7.00");
  });

  it("sumMoney", () => {
    const items = ["1.10", "2.20", "3.30"].map((s) => Money.fromStr(s));
    expect(sumMoney(items).toStorageString()).toBe("6.6000");
  });

  it("rejects garbage input", () => {
    expect(() => Money.fromStr("abc")).toThrow();
  });
});
