/**
 * Money — POS-side equivalent of backend/core/money.py.
 *
 * Storage: 4-decimal string (matches DECIMAL(14, 4) on the wire).
 * Internally we keep an integer in micropaisa (1e-4 paisa = 1e-6 rupees)
 * so arithmetic never drifts. JS numbers stay safe up to 2^53 — at
 * micropaisa precision that's roughly Rs 9 trillion, plenty of headroom.
 *
 * Per CLAUDE.md: never `float`. Always go through this utility.
 *
 * Test invariants (lib/money.test.ts):
 *   - Rs 1000 × 18% === Rs 180.00 exactly.
 *   - Adding 0.01 a hundred times === Rs 1.00 exactly.
 *   - from_str round-trips with display.
 */

const SCALE = 10_000n;  // 4 decimal places
const SCALE_NUMBER = 10_000;

export class Money {
  /** Stored as bigint at 4-decimal scale: 1.5 → 15000n. */
  readonly micro: bigint;

  private constructor(micro: bigint) {
    this.micro = micro;
  }

  static zero(): Money {
    return new Money(0n);
  }

  static fromStr(s: string | number): Money {
    if (typeof s === "number") s = s.toString();
    const trimmed = s.trim();
    if (!/^-?\d+(\.\d*)?$/.test(trimmed)) {
      throw new Error(`Money.fromStr: not a number: ${s}`);
    }
    const negative = trimmed.startsWith("-");
    const body = negative ? trimmed.slice(1) : trimmed;
    const [intPart, fracPart = ""] = body.split(".");
    // Pad/trim fraction to exactly 4 digits, half-up rounding on overflow.
    let frac = fracPart;
    if (frac.length > 4) {
      const truncated = frac.slice(0, 4);
      const next = frac[4] ?? "0";
      let rounded = BigInt(truncated);
      if (Number(next) >= 5) rounded += 1n;
      frac = rounded.toString().padStart(4, "0");
    } else {
      frac = frac.padEnd(4, "0");
    }
    const micro = BigInt(intPart) * SCALE + BigInt(frac);
    return new Money(negative ? -micro : micro);
  }

  static fromPaisa(paisa: number | bigint): Money {
    // 1 paisa = 100 micropaisa (since SCALE 10000 = 4 decimals of rupees).
    // Rs.x = paisa/100. So 12345 paisa = Rs 123.45 = 1_234_500 micro.
    return new Money(BigInt(paisa) * 100n);
  }

  add(other: Money): Money {
    return new Money(this.micro + other.micro);
  }

  sub(other: Money): Money {
    return new Money(this.micro - other.micro);
  }

  neg(): Money {
    return new Money(-this.micro);
  }

  /** Multiply by an exact decimal scalar (string for precision, or integer). */
  mulScalar(scalar: string | number): Money {
    const m = Money.fromStr(typeof scalar === "number" ? scalar.toString() : scalar);
    // (a * b) where both are 4dp → product has 8dp, we must rescale to 4dp.
    const product = (this.micro * m.micro) / SCALE;
    // Half-up rounding on the truncated remainder.
    const remainder = (this.micro * m.micro) % SCALE;
    const rounded = remainder * 2n >= SCALE ? product + 1n : product;
    return new Money(rounded);
  }

  /** Apply a percentage rate (e.g. 18 for 18%). */
  applyPct(ratePct: string | number): Money {
    const rate = Money.fromStr(typeof ratePct === "number" ? ratePct.toString() : ratePct);
    // amount × (rate / 100) → use mulScalar with rate/100 string.
    const decimalRate = (Number(rate.micro) / SCALE_NUMBER / 100).toString();
    return this.mulScalar(decimalRate);
  }

  isZero(): boolean { return this.micro === 0n; }
  isPositive(): boolean { return this.micro > 0n; }
  isNegative(): boolean { return this.micro < 0n; }

  cmp(other: Money): number {
    return this.micro < other.micro ? -1 : this.micro > other.micro ? 1 : 0;
  }

  lt(o: Money) { return this.cmp(o) < 0; }
  le(o: Money) { return this.cmp(o) <= 0; }
  gt(o: Money) { return this.cmp(o) > 0; }
  ge(o: Money) { return this.cmp(o) >= 0; }
  eq(o: Money) { return this.cmp(o) === 0; }

  /** 4-decimal string for storage / API wire format. */
  toStorageString(): string {
    const negative = this.micro < 0n;
    const abs = negative ? -this.micro : this.micro;
    const intPart = abs / SCALE;
    const frac = (abs % SCALE).toString().padStart(4, "0");
    return `${negative ? "-" : ""}${intPart}.${frac}`;
  }

  /** 2-decimal display string for receipts/UI. */
  display(): string {
    const negative = this.micro < 0n;
    const abs = negative ? -this.micro : this.micro;
    const fourDp = (abs % SCALE).toString().padStart(4, "0");
    const intPart = abs / SCALE;

    // Round 4dp to 2dp half-up
    const last2 = parseInt(fourDp.slice(2, 4), 10);
    const first2 = parseInt(fourDp.slice(0, 2), 10);
    let displayInt = intPart;
    let displayFrac = first2;
    if (last2 >= 50) {
      displayFrac += 1;
      if (displayFrac >= 100) {
        displayInt += 1n;
        displayFrac = 0;
      }
    }
    return `${negative ? "-" : ""}${displayInt}.${displayFrac.toString().padStart(2, "0")}`;
  }

  toString() { return this.toStorageString(); }
}

/**
 * Format any money value for DISPLAY at exactly 2 decimals (e.g. "1500.00").
 * Backend stores DECIMAL(14,4) so raw values arrive as "1500.0000"; this is the
 * one helper every UI price render should use so nothing ever shows ".0000".
 * Safe on null/empty/garbage (returns "0.00") — never throws, unlike
 * Money.fromStr. Use this, not raw `{value}` interpolation, for any price.
 */
export function rs(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "0.00";
  try {
    return Money.fromStr(value).display();
  } catch {
    return "0.00";
  }
}

export function sumMoney(items: Money[]): Money {
  return items.reduce((acc, m) => acc.add(m), Money.zero());
}
