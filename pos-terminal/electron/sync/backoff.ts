/**
 * Backoff schedule per the Phase 3 plan.
 *
 *   attempt 1 → 10s
 *   attempt 2 → 30s
 *   attempt 3 → 2 min
 *   attempt 4 → 10 min
 *   attempt 5 → 1 hour
 *   attempt 6 → 6 hours
 *   attempt 7+ → permanent failure (no more retries)
 *
 * Jitter: ±20% per delay. State (next_attempt_at, attempt_count) is stored
 * in SQLite so a crashed/restarted worker resumes correctly.
 */

const SCHEDULE_S = [10, 30, 120, 600, 3600, 21600];

export const MAX_ATTEMPTS = SCHEDULE_S.length;

export function backoffSeconds(attempt: number, rng: () => number = Math.random): number | null {
  if (attempt < 0) return 0;
  if (attempt >= SCHEDULE_S.length) return null;  // permanent failure
  const base = SCHEDULE_S[attempt];
  // ±20% jitter
  const jitter = 0.8 + rng() * 0.4;
  return Math.round(base * jitter);
}

export function nextAttemptAt(attempt: number, rng?: () => number): Date | null {
  const seconds = backoffSeconds(attempt, rng);
  if (seconds === null) return null;
  return new Date(Date.now() + seconds * 1000);
}
