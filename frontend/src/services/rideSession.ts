import type { RideSession } from '../types/ride';
const KEY = 'unter-ride';
export function loadSession(): RideSession {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
    return { profiles: saved?.profiles || {}, tripIds: saved?.tripIds || {}, role: saved?.role };
  } catch {
    return { profiles: {}, tripIds: {} };
  }
}
export function saveSession(session: RideSession) {
  // Merge records so two tabs don't discard the other role's profile or trip ID.
  const latest = loadSession();
  localStorage.setItem(
    KEY,
    JSON.stringify({
      ...session,
      profiles: { ...latest.profiles, ...session.profiles },
      tripIds: { ...latest.tripIds, ...session.tripIds },
    }),
  );
}
