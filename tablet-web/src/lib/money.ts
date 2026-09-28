/**
 * Money formatting for the tablet — matches the artifact's fmt().
 *
 * The waiter tablet does no fiscal math; it only DISPLAYS running totals to
 * help the waiter. Prices come off the server as DECIMAL(14,4) strings
 * (e.g. "1800.0000"); we render them as whole-rupee, thousands-separated
 * "en-PK" numbers ("1,800"), never as floats in stored math. The real
 * invoice amount is computed and fiscalised server-side / at the till.
 */

/** Parse a backend money string/number into a JS number of rupees. */
export function toRupees(value: string | number | null | undefined): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** Format a rupee amount like the artifact's fmt() — en-PK thousands, no dp. */
export function fmt(n: number): string {
  return Math.round(n).toLocaleString("en-PK");
}

/** "Rs 1,800" convenience for labels. */
export function rs(n: number): string {
  return `Rs ${fmt(n)}`;
}
