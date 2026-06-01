/**
 * Terminal-naming helpers shared by checkout + hold flows.
 *
 * The backend's per-terminal local-invoice-number generator (Phase 2)
 * keys off a terminal *index*, not the UUID. Operators set terminal
 * names like "Counter 1", "T2", "Lane 3" — we pull the first run of
 * digits out and use it as the index. Falls back to 1 when there are
 * no digits (single-terminal tenants).
 */
export function terminalIndexFromName(name: string | null | undefined): number {
  if (!name) return 1;
  const digits = name.match(/\d+/);
  return digits ? parseInt(digits[0], 10) : 1;
}
