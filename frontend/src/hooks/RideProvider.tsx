import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, api, errorMessage } from '../services/api';
import { loadSession, saveSession } from '../services/rideSession';
import { useOnline } from './useOnline';
import type {
  Driver,
  DriverOffer,
  Point,
  Profile,
  RideSession,
  Role,
  Trip,
  Zone,
  DriverEarnings,
} from '../types/ride';

interface RideData {
  zones: Zone[];
  earnings: DriverEarnings | null;
  history: Partial<Record<Role, Trip[]>>;
  driver: Driver | null;
  assignedDriver: Driver | null;
  trips: Partial<Record<Role, Trip | null>>;
  offer: DriverOffer | null;
}
interface RideContextValue extends RideData {
  session: RideSession;
  busy: boolean;
  loading: boolean;
  online: boolean;
  message: string;
  driverPoint: Point | null;
  gpsEnabled: boolean;
  clearMessage: () => void;
  createProfile: (role: Role, name: string) => Promise<void>;
  requestTrip: (pickup: Point, dropoff: Point) => Promise<void>;
  setDriverPoint: (point: Point) => void;
  enableGps: () => void;
  goOnline: () => Promise<void>;
  goOffline: () => Promise<void>;
  respond: (accept: boolean) => Promise<void>;
  cancel: () => Promise<void>;
  advance: () => Promise<void>;
}
const RideContext = createContext<RideContextValue | null>(null);
const initialData: RideData = {
  zones: [],
  earnings: null,
  history: {},
  driver: null,
  assignedDriver: null,
  trips: {},
  offer: null,
};

export function RideProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(loadSession);
  const [data, setData] = useState<RideData>(initialData);
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(''),
    [reachable, setReachable] = useState(true);
  const [driverPoint, updateDriverPoint] = useState<Point | null>(null);
  const [gpsEnabled, setGpsEnabled] = useState(false);
  const online = useOnline();
  const refs = useRef({
    session,
    data,
    point: driverPoint,
    gps: false,
    gpsAt: 0,
    lastLocation: 0,
    locked: false,
    poll: null as Promise<void> | null,
    watch: null as number | null,
    mounted: true,
  });
  const remember = useCallback((next: RideSession) => {
    refs.current.session = next;
    setSession(next);
    try {
      saveSession(next);
    } catch {
      setMessage('Couldn’t save your profile on this device.');
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!navigator.onLine) {
      setReachable(false);
      setLoading(false);
      return;
    }
    const current = refs.current;
    try {
      const zones = current.data.zones.length ? current.data.zones : await api<Zone[]>('zones');
      let nextSession = current.session;
      let driver: Driver | null = null,
        offer: DriverOffer | null = null,
        assignedDriver: Driver | null = null;
      const trips: RideData['trips'] = { ...current.data.trips };
      if (nextSession.profiles.driver) {
        driver = await api<Driver>(`drivers/${nextSession.profiles.driver.id}`);
        const position = current.gps
          ? Date.now() - current.gpsAt < 60000
            ? current.point
            : null
          : current.point || driver.position || zones[0];
        if (driver.status !== 'OFFLINE' && position && Date.now() - current.lastLocation >= 7000) {
          await api(`drivers/${driver.id}/location`, 'POST', {
            lat: position.lat,
            lon: position.lon,
          });
          current.lastLocation = Date.now();
          driver = { ...driver, position };
        }
        if (!current.point && position) {
          current.point = position;
          updateDriverPoint(position);
        }
        offer = await api<DriverOffer | null>(`drivers/${driver.id}/offer`);
        if (driver.status === 'ON_TRIP' && driver.current_trip_id) {
          nextSession = {
            ...nextSession,
            tripIds: { ...nextSession.tripIds, driver: driver.current_trip_id },
          };
        }
      }
      const history: RideData['history'] = { ...current.data.history };
      for (const role of ['passenger', 'driver'] as const) {
        const profile = nextSession.profiles[role];
        if (!profile) continue;
        const filter = role === 'passenger' ? 'riderId' : 'driverId';
        history[role] = await api<Trip[]>(`trips?${filter}=${profile.id}&limit=20`);
        const open = history[role]?.find(
          (trip) => !['COMPLETED', 'CANCELLED', 'UNMATCHED'].includes(trip.status),
        );
        if (open && nextSession.tripIds[role] !== open.id)
          nextSession = { ...nextSession, tripIds: { ...nextSession.tripIds, [role]: open.id } };
      }
      const earnings = driver ? await api<DriverEarnings>(`drivers/${driver.id}/earnings`) : null;
      for (const role of ['passenger', 'driver'] as const) {
        const id = nextSession.tripIds[role];
        if (!id) continue;
        try {
          const trip = await api<Trip>(`trips/${id}`);
          trips[role] =
            role === 'driver' && trip.driver_id !== nextSession.profiles.driver?.id ? null : trip;
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) throw error;
          trips[role] = null;
        }
      }
      if (trips.passenger?.driver_id)
        assignedDriver = await api<Driver>(`drivers/${trips.passenger.driver_id}`);
      if (nextSession !== current.session) remember(nextSession);
      const next = { zones, driver, assignedDriver, trips, offer, earnings, history };
      current.data = next;
      if (current.mounted) {
        setData(next);
        setReachable(true);
      }
    } catch (error) {
      if (refs.current.mounted) {
        setMessage(errorMessage(error));
        if (error instanceof ApiError && error.status === 0) setReachable(false);
      }
    } finally {
      if (refs.current.mounted) setLoading(false);
    }
  }, [remember]);

  useEffect(() => {
    const current = refs.current;
    current.mounted = true;
    const tick = () => {
      if (current.locked || current.poll) return;
      current.poll = refresh().finally(() => {
        current.poll = null;
      });
    };
    tick();
    const timer = window.setInterval(tick, 2500);
    const sync = () => {
      const saved = loadSession();
      current.session = saved;
      setSession(saved);
      tick();
    };
    window.addEventListener('online', tick);
    const visible = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('storage', sync);
    return () => {
      current.mounted = false;
      clearInterval(timer);
      window.removeEventListener('online', tick);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('storage', sync);
      if (current.watch !== null) navigator.geolocation.clearWatch(current.watch);
    };
  }, [refresh]);

  async function mutate(action: () => Promise<void>) {
    if (refs.current.locked) return;
    refs.current.locked = true;
    setBusy(true);
    setMessage('');
    try {
      if (refs.current.poll) await refs.current.poll;
      if (!navigator.onLine) throw new Error('You’re offline. Reconnect before making changes.');
      await action();
      await refresh();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) await refresh();
      setMessage(errorMessage(error));
    } finally {
      refs.current.locked = false;
      setBusy(false);
    }
  }
  const profile = (role: Role) => {
    const found = refs.current.session.profiles[role];
    if (!found) throw new Error('Add your name to continue.');
    return found;
  };
  const stopGps = () => {
    if (refs.current.watch !== null) navigator.geolocation.clearWatch(refs.current.watch);
    refs.current.watch = null;
    refs.current.gps = false;
    setGpsEnabled(false);
  };
  const value: RideContextValue = {
    ...data,
    session,
    busy,
    loading,
    online: online && reachable,
    message,
    driverPoint,
    gpsEnabled,
    clearMessage: () => setMessage(''),
    createProfile: (role, name) =>
      mutate(async () => {
        const created = await api<Profile>(role === 'driver' ? 'drivers' : 'riders', 'POST', {
          name: name.trim(),
        });
        remember({
          ...refs.current.session,
          profiles: { ...refs.current.session.profiles, [role]: created },
          role,
        });
      }),
    requestTrip: (pickup, dropoff) =>
      mutate(async () => {
        const trip = await api<Trip>('trips', 'POST', {
          rider_id: profile('passenger').id,
          pickup,
          dropoff,
          pickup_label: pickup.label,
          dropoff_label: dropoff.label,
        });
        remember({
          ...refs.current.session,
          tripIds: { ...refs.current.session.tripIds, passenger: trip.id },
        });
      }),
    setDriverPoint: (point) => {
      stopGps();
      refs.current.point = point;
      refs.current.lastLocation = 0;
      updateDriverPoint(point);
    },
    enableGps: () => {
      if (!navigator.geolocation) {
        setMessage('Location is unavailable. Select a point on the map.');
        return;
      }
      stopGps();
      refs.current.gps = true;
      setGpsEnabled(true);
      refs.current.gpsAt = 0;
      refs.current.watch = navigator.geolocation.watchPosition(
        (position) => {
          const point = { lat: position.coords.latitude, lon: position.coords.longitude };
          refs.current.point = point;
          refs.current.gpsAt = Date.now();
          updateDriverPoint(point);
        },
        () => setMessage('Allow location access or choose a spot on the map.'),
        { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 },
      );
    },
    goOnline: () =>
      mutate(async () => {
        if (refs.current.gps && Date.now() - refs.current.gpsAt >= 60000)
          throw new Error(
            'Waiting for a fresh GPS position. You can also select a point on the map.',
          );
        const point =
          refs.current.point || refs.current.data.driver?.position || refs.current.data.zones[0];
        if (!point) throw new Error('Choose your location first.');
        const id = profile('driver').id;
        await api(`drivers/${id}/location`, 'POST', { lat: point.lat, lon: point.lon });
        refs.current.lastLocation = Date.now();
        await api(`drivers/${id}/online`, 'POST');
      }),
    goOffline: () =>
      mutate(async () => {
        await api(`drivers/${profile('driver').id}/offline`, 'POST');
      }),
    respond: (accept) =>
      mutate(async () => {
        const offer = refs.current.data.offer;
        if (!offer || Date.parse(offer.offer.expires_at) <= Date.now())
          throw new Error('This offer expired. Waiting for another request.');
        const result = await api<{ trip: Trip }>(
          `offers/${offer.offer.id}/${accept ? 'accept' : 'reject'}`,
          'POST',
          { driver_id: profile('driver').id },
        );
        if (accept)
          remember({
            ...refs.current.session,
            tripIds: { ...refs.current.session.tripIds, driver: result.trip.id },
          });
      }),
    cancel: () =>
      mutate(async () => {
        const trip = refs.current.data.trips.passenger;
        if (trip)
          await api(`trips/${trip.id}/cancel`, 'POST', { rider_id: profile('passenger').id });
      }),
    advance: () =>
      mutate(async () => {
        const trip = refs.current.data.trips.driver;
        if (trip)
          await api(
            `trips/${trip.id}/${trip.status === 'ASSIGNED' ? 'pickup' : 'complete'}`,
            'POST',
            { driver_id: profile('driver').id },
          );
      }),
  };
  return <RideContext.Provider value={value}>{children}</RideContext.Provider>;
}
export function useRide() {
  const value = useContext(RideContext);
  if (!value) throw new Error('useRide requires RideProvider');
  return value;
}
