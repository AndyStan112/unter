const $ = id => document.getElementById(id);
const terminal = trip => !trip || ['COMPLETED', 'CANCELLED', 'UNMATCHED'].includes(trip.status);
const labels = {
  REQUESTED: 'Finding your driver', OFFERED: 'Waiting for a driver to accept',
  ASSIGNED: 'Your driver is on the way', PICKED_UP: 'Enjoy the ride',
  COMPLETED: 'You’ve arrived', CANCELLED: 'Ride cancelled', UNMATCHED: 'No driver available. Try again.'
};
let saved;
try { saved = JSON.parse(localStorage.getItem('unter-ride') || '{}') || {}; } catch { saved = {}; }
const profiles = saved.profiles || {}, tripIds = saved.tripIds || {};
let role = saved.role === 'driver' ? 'driver' : 'passenger';
let zones = [], trip = null, driver = null, assignedDriver = null, offer = null;
let busy = false, poll = null, connected = navigator.onLine !== false;
let gps = null, gpsWatch = null, lastLocation = 0, installPrompt;

function persist() {
  try { localStorage.setItem('unter-ride', JSON.stringify({profiles, tripIds, role})); }
  catch { notice('Browser storage is unavailable. Keep this page open to retain your profile.'); }
}
function notice(message = '') { $('notice').textContent = message; }
async function api(path, method = 'GET', body) {
  let response;
  try {
    response = await fetch('/api/' + path, {
      method, credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(12000),
      headers: {'Content-Type': 'application/json', 'X-Unter-Request': '1'},
      ...(body ? {body: JSON.stringify(body)} : {})
    });
  } catch {
    connected = false;
    throw new Error('Connection lost. Reconnect to get live updates and make changes.');
  }
  connected = true;
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const error = new Error(response.status === 401 ? 'Sign in with the server’s shared development login, then retry.' :
      data?.message || data?.detail || `Request failed (${response.status})`);
    error.status = response.status;
    error.code = data?.error;
    throw error;
  }
  return data;
}
function point(id) {
  const zone = zones[Number($(id).value)];
  if (!zone) throw new Error('Wait for locations to load.');
  return {lat: zone.lat, lon: zone.lon};
}
function locationText(point) {
  if (!point) return 'Location unavailable';
  const zone = zones.find(z => Math.abs(z.lat - point.lat) < 0.00001 && Math.abs(z.lon - point.lon) < 0.00001);
  return zone?.name || `${Number(point.lat).toFixed(4)}, ${Number(point.lon).toFixed(4)}`;
}
function action(text, fn, disabled = false) {
  const button = document.createElement('button');
  button.textContent = text;
  button.disabled = busy || !connected || disabled;
  button.onclick = () => run(fn);
  $('trip-actions').append(button);
}
function render() {
  const profile = profiles[role];
  for (const r of ['passenger', 'driver']) {
    $(r).setAttribute('aria-pressed', String(role === r));
    $(r).disabled = busy;
  }
  $('profile').hidden = !!profile;
  $('workspace').hidden = !profile;
  $('profile').querySelector('button').textContent = 'Continue as ' + role;
  document.querySelectorAll('form button').forEach(button => button.disabled = busy || !connected);
  $('booking').querySelector('button').disabled = busy || !connected || !zones.length;
  $('connection').textContent = !connected ? 'Offline · showing the last known status' : busy ? 'Updating…' : 'Live · updates every 2.5 seconds';
  if (!profile) return;
  $('greeting').textContent = `Hi, ${profile.name}`;
  $('booking').hidden = role !== 'passenger' || !terminal(trip);
  $('driver-controls').hidden = role !== 'driver';
  $('driver-status').textContent = driver ? `Status: ${driver.status.toLowerCase().replaceAll('_', ' ')}` : 'Loading driver…';
  $('online').disabled = busy || !connected || !zones.length || !driver || driver.status !== 'OFFLINE';
  $('offline').disabled = busy || !connected || !driver || ['OFFLINE', 'ON_TRIP'].includes(driver.status);
  $('trip-actions').replaceChildren();
  const current = offer?.trip || trip;
  $('trip').hidden = !current;
  if (!current) return;
  $('trip-label').textContent = offer ? 'INCOMING REQUEST' : 'YOUR RIDE';
  $('trip-status').textContent = offer ? 'A passenger needs a ride' :
    role === 'driver' && current.status === 'ASSIGNED' ? 'Head to the pickup' : labels[current.status] || current.status;
  $('trip-route').textContent = `${locationText(current.pickup)} → ${locationText(current.dropoff)}`;
  const price = current.price ?? offer?.estimated_price;
  $('trip-price').textContent = price == null ? 'Fare confirmed when your driver accepts.' :
    `${Number(price).toFixed(2)} RON${offer ? ' · estimated' : ''}`;
  $('trip-detail').textContent = offer ? `Respond by ${new Date(offer.offer.expires_at).toLocaleTimeString()}` :
    role === 'passenger' && current.driver_id ?
      `Driver: ${assignedDriver?.name || current.driver_id.slice(0, 8)}${assignedDriver?.position ? ' · ' + locationText(assignedDriver.position) : ''}` : '';
  if (offer) {
    const id = offer.offer.id, expired = Date.parse(offer.offer.expires_at) <= Date.now();
    action(expired ? 'Offer expired' : 'Accept ride', async () => {
      const result = await api(`offers/${id}/accept`, 'POST', {driver_id: profile.id});
      trip = result.trip; tripIds.driver = trip.id; offer = null; persist();
    }, expired);
    action('Decline', async () => {
      await api(`offers/${id}/reject`, 'POST', {driver_id: profile.id}); offer = null;
    }, expired);
  } else if (role === 'passenger' && ['REQUESTED', 'OFFERED', 'ASSIGNED'].includes(current.status)) {
    action('Cancel ride', async () => { trip = await api(`trips/${current.id}/cancel`, 'POST', {rider_id: profile.id}); });
  } else if (role === 'driver' && ['ASSIGNED', 'PICKED_UP'].includes(current.status)) {
    action(current.status === 'ASSIGNED' ? 'Confirm pickup' : 'Complete ride', async () => {
      trip = await api(`trips/${current.id}/${current.status === 'ASSIGNED' ? 'pickup' : 'complete'}`, 'POST', {driver_id: profile.id});
    });
  }
}
async function loadZones() {
  if (zones.length) return;
  zones = await api('zones');
  for (const id of ['pickup', 'dropoff', 'driver-zone']) {
    $(id).replaceChildren(...zones.map((zone, i) => {
      const option = document.createElement('option'); option.value = i; option.textContent = zone.name; return option;
    }));
  }
  if (zones.length > 1) $('dropoff').value = '1';
}
async function refresh() {
  if (navigator.onLine === false) {
    connected = false;
    notice('You’re offline. Reconnect to load live status and make changes.');
    render(); return;
  }
  await loadZones();
  // Keep the driver's heartbeat going even when this browser displays passenger mode.
  if (profiles.driver) {
    driver = await api(`drivers/${profiles.driver.id}`);
    if (driver.status !== 'OFFLINE' && Date.now() - lastLocation >= 7000) {
      const position = gps && Date.now() - gps.at < 60000 ? {lat: gps.lat, lon: gps.lon} :
        gpsWatch !== null ? null : point('driver-zone');
      if (position) {
        await api(`drivers/${driver.id}/location`, 'POST', position); lastLocation = Date.now();
      } else notice('Waiting for a fresh GPS position. Select a zone if GPS is unavailable.');
    }
  }
  if (!profiles[role]) { render(); return; }
  offer = null;
  if (role === 'driver') {
    offer = await api(`drivers/${driver.id}/offer`);
    // OFFERED is not an accepted trip. Declining it must not retain its trip ID.
    if (driver.status === 'ON_TRIP' && driver.current_trip_id) {
      tripIds.driver = driver.current_trip_id; persist();
    }
  }
  if (tripIds[role]) {
    try { trip = await api(`trips/${tripIds[role]}`); }
    catch (error) {
      if (error.status !== 404) throw error;
      delete tripIds[role]; trip = null; persist();
    }
    if (role === 'driver' && trip?.driver_id !== profiles.driver.id) {
      delete tripIds.driver; trip = null; persist();
    }
  } else trip = null;
  assignedDriver = role === 'passenger' && trip?.driver_id && !terminal(trip) ?
    await api(`drivers/${trip.driver_id}`) : null;
  render();
}
async function run(fn) {
  if (busy) return;
  busy = true; notice(); render();
  try {
    // Let an in-flight poll finish before switching role or mutating its state.
    if (poll) await poll;
    if (navigator.onLine === false || !connected) throw new Error('You’re offline. Reconnect before making changes.');
    await fn();
    await refresh();
  } catch (error) {
    if (error.status === 409) {
      try { await refresh(); } catch { /* Keep the original conflict visible. */ }
    }
    notice(error.message);
  } finally { busy = false; render(); }
}
function tick() {
  if (busy || poll) return poll;
  poll = refresh().catch(error => { notice(error.message); render(); }).finally(() => { poll = null; });
  return poll;
}
for (const r of ['passenger', 'driver']) $(r).onclick = () => run(async () => {
  role = r; trip = null; offer = null; assignedDriver = null; persist(); render();
});
$('profile').onsubmit = event => {
  event.preventDefault();
  return run(async () => {
    const name = $('name').value.trim();
    if (!name) throw new Error('Enter your name.');
    profiles[role] = await api(role === 'driver' ? 'drivers' : 'riders', 'POST', {name}); persist();
  });
};
$('booking').onsubmit = event => {
  event.preventDefault();
  return run(async () => {
    const pickup = point('pickup'), dropoff = point('dropoff');
    if (pickup.lat === dropoff.lat && pickup.lon === dropoff.lon) throw new Error('Choose a different destination.');
    trip = await api('trips', 'POST', {rider_id: profiles.passenger.id, pickup, dropoff});
    tripIds.passenger = trip.id; persist();
  });
};
$('online').onclick = () => run(async () => {
  if (gpsWatch !== null && (!gps || Date.now() - gps.at >= 60000)) throw new Error('Wait for a fresh GPS position, or select a zone.');
  const position = gpsWatch !== null ? {lat: gps.lat, lon: gps.lon} : point('driver-zone');
  await api(`drivers/${profiles.driver.id}/location`, 'POST', position); lastLocation = Date.now();
  await api(`drivers/${profiles.driver.id}/online`, 'POST');
});
$('offline').onclick = () => run(() => api(`drivers/${profiles.driver.id}/offline`, 'POST'));
function stopGps() {
  if (gpsWatch !== null) navigator.geolocation.clearWatch(gpsWatch);
  gpsWatch = null; gps = null;
}
$('driver-zone').onchange = () => {
  stopGps(); lastLocation = 0; $('location-note').textContent = 'Selected zone center is being used as your location.';
};
$('gps').onclick = () => {
  if (!navigator.geolocation) return notice('GPS is unavailable. Select a zone instead.');
  stopGps();
  $('location-note').textContent = 'Waiting for GPS permission and a fresh position…';
  gpsWatch = navigator.geolocation.watchPosition(position => {
    gps = {lat: position.coords.latitude, lon: position.coords.longitude, at: Date.now()};
    $('location-note').textContent = 'Live GPS enabled. Select a zone to stop using GPS.';
  }, () => {
    gps = null; notice('Location unavailable. Select a zone or allow location access.');
  }, {enableHighAccuracy: true, timeout: 10000, maximumAge: 0});
};
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); installPrompt = event; $('install').hidden = false;
});
$('install').onclick = async () => {
  if (!installPrompt) return;
  const prompt = installPrompt; installPrompt = null; $('install').hidden = true;
  await prompt.prompt();
};
window.addEventListener('appinstalled', () => { $('install').hidden = true; });
window.addEventListener('offline', () => {
  connected = false; notice('You’re offline. Ride actions need a connection. Showing the last known status.'); render();
});
window.addEventListener('online', () => { connected = true; notice(); tick(); });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/ride/sw.js', {scope: '/ride/'})
  .catch(() => notice('Offline setup unavailable. You can still use the app while connected.'));
render(); tick();
setInterval(tick, 2500);
