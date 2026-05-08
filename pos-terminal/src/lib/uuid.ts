/**
 * UUID helpers for the POS terminal.
 *
 * The renderer uses crypto.randomUUID() (v4). v7 (time-ordered) lives on the
 * server; idempotency only needs uniqueness, not ordering, so v4 is fine
 * here.
 */

export function newClientUuid(): string {
  return crypto.randomUUID();
}
