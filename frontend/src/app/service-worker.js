// Build substitutes a version and the complete list of hashed local assets.
const CACHE = 'unter-ride-shell-__CACHE_VERSION__';
const ASSETS = __PRECACHE_ASSETS__;
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting()),
  );
});
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('unter-ride-shell-') && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  // API data, dashboard HTML and external map tiles never enter this cache.
  const asset = url.pathname + url.search;
  const navigation =
    !url.search &&
    event.request.mode === 'navigate' &&
    ['/ride/', '/ride/index.html', '/ride/passenger', '/ride/driver'].includes(url.pathname);
  if (!navigation && !ASSETS.includes(asset)) return;
  if (!navigation) {
    // Content-hashed assets are immutable; static icons/manifest stay network-first.
    if (url.pathname.startsWith('/assets/')) {
      event.respondWith(
        caches.match(event.request).then((cached) => cached || fetch(event.request)),
      );
      return;
    }
  }
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && ASSETS.includes(asset)) {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(event.request, copy)));
        }
        return response;
      })
      .catch(
        async () =>
          (await caches.match(navigation ? '/ride/index.html' : event.request)) || Response.error(),
      ),
  );
});
