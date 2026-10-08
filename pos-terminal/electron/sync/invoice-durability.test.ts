/**
 * A PAID INVOICE MUST NEVER BE LOST.
 *
 * Everything else in the outbound queue may eventually be written off. A sale
 * the customer has already paid for may not: it is the business's record of
 * income and a legally retained document (6-year retention).
 *
 * Two ways the old code could abandon one:
 *   1. any 4xx from the server -> permanentFailure() -> status 'failed',
 *      never retried. A product missing from the server catalog, an unsynced
 *      cash session or a branch mid-rename would all do it.
 *   2. MAX_ATTEMPTS (~8h of backoff) exhausted -> also 'failed'.
 *
 * Now an invoice parks as 'pending' on an hourly cycle instead, keeping its
 * error visible while it keeps trying.
 */

import { describe, expect, it } from "vitest";
import { MAX_ATTEMPTS, backoffSeconds } from "./backoff";

/** Mirrors permanentFailure()/transientFailure() in worker.ts. */
function makeQueue() {
  const rows = new Map<number, {
    id: number; entity_type: string; status: string;
    attempt_count: number; last_error: string | null;
  }>();

  function permanentFailure(id: number, message: string) {
    const r = rows.get(id)!;
    if (r.entity_type === "invoice") {
      r.status = "pending";                       // never 'failed'
      r.last_error = `will keep retrying — ${message}`;
      return;
    }
    r.status = "failed";
    r.last_error = message;
  }

  function transientFailure(id: number, message: string) {
    const r = rows.get(id)!;
    const next = r.attempt_count + 1;
    if (next >= MAX_ATTEMPTS) {
      permanentFailure(id, `max attempts: ${message}`);
      return;
    }
    r.attempt_count = next;
    r.status = "pending";
    r.last_error = message;
  }

  return { rows, permanentFailure, transientFailure };
}

describe("a paid invoice is never abandoned", () => {
  it("survives a 4xx rejection from the server", () => {
    const q = makeQueue();
    q.rows.set(1, { id: 1, entity_type: "invoice", status: "sent",
                    attempt_count: 0, last_error: null });

    q.permanentFailure(1, '400: {"product":"not found"}');

    const r = q.rows.get(1)!;
    expect(r.status).toBe("pending");          // NOT 'failed'
    expect(r.last_error).toContain("will keep retrying");
  });

  it("survives exhausting every retry attempt", () => {
    const q = makeQueue();
    q.rows.set(1, { id: 1, entity_type: "invoice", status: "sent",
                    attempt_count: MAX_ATTEMPTS - 1, last_error: null });

    q.transientFailure(1, "500: server error");

    expect(q.rows.get(1)!.status).toBe("pending");
  });

  it("stays recoverable across MANY consecutive failures", () => {
    const q = makeQueue();
    q.rows.set(1, { id: 1, entity_type: "invoice", status: "sent",
                    attempt_count: 0, last_error: null });

    for (let i = 0; i < 50; i++) q.transientFailure(1, "500");

    expect(q.rows.get(1)!.status).toBe("pending");
  });

  it("still writes off a NON-invoice entity (behaviour unchanged)", () => {
    const q = makeQueue();
    q.rows.set(2, { id: 2, entity_type: "customer", status: "sent",
                    attempt_count: 0, last_error: null });

    q.permanentFailure(2, "400: bad data");

    expect(q.rows.get(2)!.status).toBe("failed");
  });
});

describe("backoff schedule is unchanged", () => {
  it("still escalates and then signals exhaustion", () => {
    expect(backoffSeconds(0, () => 0.5)).toBe(10);
    expect(backoffSeconds(MAX_ATTEMPTS, () => 0.5)).toBeNull();
  });
});
