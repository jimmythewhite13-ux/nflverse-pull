// Real, minimal service worker -- makes the page installable (a real PWA requirement) without
// caching real, live game/injury/market data (those must always be fetched fresh; caching them
// would risk showing stale real data as if it were current).
const SHELL_CACHE = "nfl-model-shell-v1";
const SHELL_FILES = ["/", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Real API calls: always go to the network, never served from cache -- real, live data only.
  if (url.pathname.startsWith("/sports")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
