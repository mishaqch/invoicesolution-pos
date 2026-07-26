import { lazy, type ComponentType } from "react";

/**
 * lazy() that auto-recovers from a STALE-CHUNK 404.
 *
 * Each route is a content-hashed chunk (login-D0Dvl2iS.js). When we deploy, the
 * hashes change and old chunk files are deleted. A browser tab that was opened
 * BEFORE the deploy is still running the old JS in memory, which knows the old
 * chunk names — so the first time it lazy-imports a route that wasn't already
 * downloaded (e.g. the login page after logout), the fetch 404s and React shows
 * a blank screen with "Failed to fetch dynamically imported module".
 *
 * The only reliable fix is a full page reload: that re-fetches the fresh
 * index.html (served no-cache) which points at the new chunk names. We do it
 * ONCE per failing chunk, guarded by sessionStorage so a genuinely-broken chunk
 * (or an offline user) can't get stuck in a reload loop — on the second failure
 * we rethrow so the error boundary / normal error handling takes over.
 */
export function lazyWithReload<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
  key: string,
): React.LazyExoticComponent<T> {
  return lazy(async () => {
    const flag = `chunk-reload:${key}`;
    try {
      const mod = await factory();
      // Success — clear any prior reload flag for this chunk.
      sessionStorage.removeItem(flag);
      return mod;
    } catch (err) {
      // Already tried a reload for this chunk this session → don't loop.
      if (sessionStorage.getItem(flag)) throw err;
      sessionStorage.setItem(flag, "1");
      // Force a fresh index.html + new chunk names. This navigation aborts the
      // current render; the returned promise never needs to resolve.
      window.location.reload();
      // Keep the promise pending until the reload takes over.
      return new Promise<{ default: T }>(() => {});
    }
  });
}
