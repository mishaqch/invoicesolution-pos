/* Hand-written service worker for the waiter tablet PWA.
 *
 * Strategy:
 *   - Precache the app shell so the tablet boots even on a flaky link.
 *   - /api/* is NETWORK-ONLY and never cached — order data must be live; a
 *     stale menu or a cached order would be dangerous in a restaurant.
 *   - Everything else is cache-first, falling back to offline.html for a
 *     failed navigation.
 *
 * This is an ONLINE-ONLY client — firing/saving orders needs the network. The
 * SW is a boot-resilience nicety, not an offline order queue.
 */
const CACHE = "tablet-shell-v1";
const APP_SHELL = ["/", "/index.html", "/manifest.json", "/offline.html"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin GETs; let the browser do everything else.
  if (req.method !== "GET" || url.origin !== self.location.origin) return;

  // API calls: network-only, never cached.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(req));
    return;
  }

  // Navigations: network first, fall back to the cached shell, then offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match("/index.html").then((r) => r || caches.match("/offline.html")),
      ),
    );
    return;
  }

  // Static assets: cache-first, then network (and cache the result).
  event.respondWith(
    caches.match(req).then(
      (cached) =>
        cached ||
        fetch(req).then((resp) => {
          if (resp && resp.status === 200 && resp.type === "basic") {
            const copy = resp.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return resp;
        }),
    ),
  );
});
