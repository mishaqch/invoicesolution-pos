/**
 * Printer-interface normalization (pure, dependency-free so it is unit-testable
 * without pulling in React/UI modules).
 *
 * A WiFi/network thermal printer is reached over raw TCP on port 9100 (standard
 * ESC/POS). If the user types just an IP ("192.168.1.20") or an IP with a port
 * ("192.168.1.20:9100"), we turn it into a proper "tcp://IP:9100" URI so the
 * print path treats it as a NETWORK printer — not as a Windows printer name
 * (which is what a bare string would otherwise be interpreted as). Anything that
 * already carries a scheme (tcp://, win:, cups://, serial:, /dev/…, //share) or
 * looks like a Windows printer name is left untouched.
 */
export function normalizeKitchenInterface(raw: string): string {
  const s = (raw || "").trim();
  if (!s) return "";
  // Already a scheme'd interface or a device/share path — leave it.
  if (/^(tcp:\/\/|cups:\/\/|win:|serial:|\/dev\/|\/\/)/i.test(s)) return s;
  // Bare IPv4 → tcp://IP:9100
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(s)) return `tcp://${s}:9100`;
  // IPv4:port or host:port → tcp://host:port
  if (/^[a-z0-9.-]+:\d+$/i.test(s)) return `tcp://${s}`;
  // Otherwise it's a Windows printer name; the print layer prefixes win:.
  return s;
}
