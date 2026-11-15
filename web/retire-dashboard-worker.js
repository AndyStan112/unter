// Update only the legacy root worker, leaving the ride app registration alone.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(registrations => Promise.all(
    registrations.filter(registration => registration.scope === new URL('/', location.href).href)
      .filter(registration => [registration.active, registration.waiting, registration.installing]
        .some(worker => worker && new URL(worker.scriptURL).pathname === '/sw.js'))
      .map(registration => registration.update())
  )).catch(() => { /* Retry retirement on the next online visit. */ });
}
