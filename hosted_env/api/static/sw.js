// Real, minimal service worker -- makes the page installable (a real PWA requirement) without
// caching real, live game/injury/market data (those must always be fetched fresh; caching them
// would risk showing stale real data as if it were current).
//
// Real bug found and fixed (2026-09-11): the original version used cache-FIRST for the app
// shell ("/", manifest, icon) -- once installed, a returning visitor kept seeing whatever
// index.html/CSS/JS existed at install time forever, with no way to pick up a real update
// short of the visitor manually clearing site data. Confirmed directly: this session's own
// local testing kept serving a stale, pre-redesign index.html after a real edit, with zero
// errors to explain it. Real fix: NETWORK-first for the shell (always try live first, only
// fall back to cache when genuinely offline) + a bumped cache name with old-cache cleanup on
// activate, so anyone who already installed the old, cache-first version also recovers.
// Real, bumped cache version (2026-09-11): the frontend architecture refactor split one
// monolithic index.html into real, separate css/js files -- the old cache's stale, pre-refactor
// shell entries (if any survived offline) shouldn't linger under the same cache name.
const SHELL_CACHE = "nfl-model-shell-v3";
const SHELL_FILES = [
  "/", "/manifest.json", "/icon.svg", "/css/app.css",
  "/js/app.js", "/js/api.js", "/js/state.js", "/js/format.js",
  "/js/market-signals.js", "/js/week-caveat.js", "/js/views.js",
  "/js/detail.js", "/js/week-nav.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n !== SHELL_CACHE).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Real API calls: always go to the network, never served from cache -- real, live data only.
  if (url.pathname.startsWith("/sports")) {
    return;
  }
  // Real, deliberate network-first for the app shell: a returning visitor with a live
  // connection always gets the real, current shell; the cached copy is only ever a fallback
  // for genuinely being offline.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
