// Retire the former dashboard PWA on its next online visit.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil((async () => {
  for (const key of await caches.keys()) {
    if (key.startsWith('unter-shell-')) await caches.delete(key);
  }
  await self.registration.unregister();
})()));
