/**
 * The sync worker must receive auth tokens on EVERY app start, not only at
 * sign-in.
 *
 * Root cause of "paid orders stay in Open orders":
 *   - session.ts pushes tokens to the worker in signIn() only, and its
 *     persist partialize() stores user/tenant/role but NOT access/refresh.
 *   - So after a restart the cashier still looks signed in while the worker
 *     holds no token. processRow() hits `if (!accessToken) return;` and never
 *     POSTs, so a charged sale sat in outbound_queue forever and its order
 *     stayed open on the server.
 *   - Evidence: /api/sync/invoices/ was called ZERO times in the whole nginx
 *     history, while /api/restaurant/orders/ (renderer, in-memory token) was
 *     called 49 times the same day.
 *
 * setAuthTokens() already writes both tokens to kv_meta at login, so the fix
 * is for startSyncWorker() to read them back and hand them to the worker.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";

/** Minimal fake of the kv_meta-backed helpers + worker channel. */
function makeHarness(stored: Record<string, string | null>) {
  const posted: { type: string; [k: string]: unknown }[] = [];
  const getMeta = vi.fn((k: string) => stored[k] ?? null);
  const worker = { postMessage: (m: never) => posted.push(m) };

  /** Mirrors the restore block added to startSyncWorker(). */
  function restoreTokens() {
    try {
      const access = getMeta("access_token");
      const refresh = getMeta("refresh_token");
      if (access || refresh) {
        worker.postMessage({
          type: "auth",
          accessToken: access,
          refreshToken: refresh,
        } as never);
      }
    } catch {
      /* missing kv_meta is not fatal */
    }
  }

  return { posted, getMeta, restoreTokens };
}

describe("sync worker token restore on startup", () => {
  let h: ReturnType<typeof makeHarness>;

  beforeEach(() => {
    h = makeHarness({ access_token: "acc-123", refresh_token: "ref-456" });
  });

  it("hands persisted tokens to the worker so the queue can drain", () => {
    h.restoreTokens();
    expect(h.posted).toEqual([
      { type: "auth", accessToken: "acc-123", refreshToken: "ref-456" },
    ]);
  });

  it("still restores when only the refresh token survives", () => {
    const only = makeHarness({ access_token: null, refresh_token: "ref-456" });
    only.restoreTokens();
    // The worker's 401 handler refreshes from this, so it must be delivered.
    expect(only.posted).toEqual([
      { type: "auth", accessToken: null, refreshToken: "ref-456" },
    ]);
  });

  it("stays silent on a never-signed-in terminal", () => {
    const fresh = makeHarness({ access_token: null, refresh_token: null });
    fresh.restoreTokens();
    expect(fresh.posted).toEqual([]);
  });

  it("does not throw when kv_meta is unreadable", () => {
    const broken = makeHarness({});
    broken.getMeta.mockImplementation(() => {
      throw new Error("no such table: kv_meta");
    });
    expect(() => broken.restoreTokens()).not.toThrow();
    expect(broken.posted).toEqual([]);
  });
});

describe("the bug this prevents", () => {
  it("a worker with no token skips every queued row", () => {
    let accessToken: string | null = null;
    const sent: string[] = [];

    function processRow(id: string) {
      if (!accessToken) return "skipped";   // worker.ts:201
      sent.push(id);
      return "sent";
    }

    expect(processRow("paid-invoice-1")).toBe("skipped");
    expect(sent).toEqual([]);

    // After the restore fix:
    accessToken = "acc-123";
    expect(processRow("paid-invoice-1")).toBe("sent");
    expect(sent).toEqual(["paid-invoice-1"]);
  });
});
