/**
 * Pakistan-local time helpers (pure). Forcing Asia/Karachi means printed KOT /
 * receipt times are correct even when the terminal PC's Windows clock is set to
 * the wrong timezone — a common on-site misconfiguration. Kept dependency-free
 * so it is unit-testable.
 */
const PK_TZ = "Asia/Karachi";

/** "HH:MM" in Pakistan time (24h). */
export function pkTimeHHMM(d: Date = new Date()): string {
  return d.toLocaleTimeString("en-GB", {
    timeZone: PK_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** "YYYY-MM-DD" in Pakistan time (matches the server's Asia/Karachi invoice_date). */
export function pkDate(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: PK_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}
