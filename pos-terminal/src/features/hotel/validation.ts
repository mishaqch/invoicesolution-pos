/**
 * Pakistan CNIC + mobile validation / formatting for guest records.
 *
 * CNIC:  exactly 13 digits, written XXXXX-XXXXXXX-X (15 chars incl. dashes).
 * Mobile: 11 digits starting 03 (03XX-XXXXXXX). +92 / 92 / 0092 prefixes are
 *         accepted and normalised to the local 03XXXXXXXXX form.
 *
 * All canonical forms stay well under the server's 20-char guest_cnic/phone
 * limit (the source of the "characters not more than 20" error).
 */

export const digitsOnly = (s: string) => (s || "").replace(/\D/g, "");

export function isValidCnic(raw: string): boolean {
  return digitsOnly(raw).length === 13;
}
export function formatCnic(raw: string): string {
  const d = digitsOnly(raw).slice(0, 13);
  if (d.length !== 13) return d;
  return `${d.slice(0, 5)}-${d.slice(5, 12)}-${d.slice(12)}`;
}

export function normalizePkMobile(raw: string): string {
  let d = digitsOnly(raw);
  if (d.startsWith("0092")) d = d.slice(4);
  else if (d.startsWith("92")) d = d.slice(2);
  if (d.length === 10 && d.startsWith("3")) d = "0" + d;
  return d;
}
export function isValidPkMobile(raw: string): boolean {
  const d = normalizePkMobile(raw);
  return d.length === 11 && d.startsWith("03");
}
export function formatPkMobile(raw: string): string {
  const d = normalizePkMobile(raw);
  if (d.length !== 11) return d;
  return `${d.slice(0, 4)}-${d.slice(4)}`;
}

// Live input masks — format progressively as the cashier types.
export function cnicMask(raw: string): string {
  const d = digitsOnly(raw).slice(0, 13);
  if (d.length <= 5) return d;
  if (d.length <= 12) return `${d.slice(0, 5)}-${d.slice(5)}`;
  return `${d.slice(0, 5)}-${d.slice(5, 12)}-${d.slice(12)}`;
}
export function phoneMask(raw: string): string {
  let d = digitsOnly(raw);
  if (d.startsWith("0092")) d = "0" + d.slice(4);
  else if (d.startsWith("92")) d = "0" + d.slice(2);
  d = d.slice(0, 11);
  if (d.length <= 4) return d;
  return `${d.slice(0, 4)}-${d.slice(4)}`;
}
