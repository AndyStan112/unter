import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RideProvider, useRide } from './RideProvider';
import { saveSession } from '../services/rideSession';
import type { Driver, DriverOffer, Trip } from '../types/ride';

const zones = [
  { name: 'Centru', lat: 45.7537, lon: 21.2257 },
  { name: 'Fabric', lat: 45.759, lon: 21.251 },
];
function backend() {
  let driver: Driver = {
    id: 'd1',
    name: 'Dan',
    status: 'OFFLINE',
    current_trip_id: null,
    position: zones[0],
    position_updated_at: null,
    zone: 'Centru',
  };
  let trip: Trip = {
    id: 't1',
    rider_id: 'r1',
    driver_id: null,
    status: 'OFFERED',
    zone: 'Centru',
    pickup: zones[0],
    dropoff: zones[1],
    price: null,
    surge_multiplier: null,
  };
  let offer: DriverOffer | null = null,
    gate: Promise<void> | null = null,
    conflict = false,
    booked = false;
  const fetcher = vi.fn(async (url: string, options: RequestInit) => {
    if (gate) {
      const current = gate;
      gate = null;
      await current;
    }
    const path = url.replace('/api/', '');
    if (conflict && path.endsWith('/accept')) {
      ((conflict = false), (booked = false));
      return new Response(JSON.stringify({ message: 'Offer expired' }), { status: 409 });
    }
    let data: unknown = null;
    if (path === 'trips' && options.method === 'POST') {
      booked = true;
      data = trip;
    } else if (path === 'zones') data = zones;
    else if (path === 'riders') data = { id: 'r1', name: 'Ana' };
    else if (path === 'drivers') data = driver;
    else if (path.endsWith('/location')) {
      driver = { ...driver, position: JSON.parse(String(options.body)) };
    } else if (path.endsWith('/online')) {
      driver = { ...driver, status: 'AVAILABLE' };
      data = driver;
    } else if (path.endsWith('/offline')) {
      driver = { ...driver, status: 'OFFLINE' };
      data = driver;
    } else if (path.endsWith('/offer')) data = offer;
    else if (path.endsWith('/earnings'))
      data = {
        balance: trip.status === 'COMPLETED' ? 18 : 0,
        fares: 15,
        bonuses: 3,
        today: 18,
        completed_trips: 1,
        entries: [],
        mode: 'mock',
        currency: 'RON',
      };
    else if (path.startsWith('trips?'))
      data = path.includes('driverId')
        ? trip.driver_id === driver.id
          ? [trip]
          : []
        : booked
          ? [trip]
          : [];
    else if (path.startsWith('drivers/')) data = driver;
    else if (path.endsWith('/accept')) {
      trip = { ...trip, status: 'ASSIGNED', driver_id: driver.id, price: 15 };
      driver = { ...driver, status: 'ON_TRIP', current_trip_id: trip.id };
      data = { trip };
      offer = null;
    } else if (path.endsWith('/reject')) {
      offer = null;
      driver = { ...driver, status: 'AVAILABLE', current_trip_id: null };
      data = {};
    } else if (path.endsWith('/pickup')) {
      trip = { ...trip, status: 'PICKED_UP' };
      data = trip;
    } else if (path.endsWith('/complete')) {
      trip = { ...trip, status: 'COMPLETED' };
      driver = { ...driver, status: 'AVAILABLE', current_trip_id: null };
      data = trip;
    } else if (path.endsWith('/cancel')) {
      trip = { ...trip, status: 'CANCELLED' };
      data = trip;
    } else data = trip;
    return data === null ? new Response(null, { status: 204 }) : new Response(JSON.stringify(data));
  });
  vi.stubGlobal('fetch', fetcher);
  return {
    fetcher,
    delay: (promise: Promise<void>) => {
      gate = promise;
    },
    conflict: () => {
      conflict = true;
    },
    incoming: () => {
      driver = { ...driver, status: 'OFFERED', current_trip_id: trip.id };
      offer = {
        offer: {
          id: 'o1',
          status: 'PENDING',
          expires_at: new Date(Date.now() + 30000).toISOString(),
        },
        trip,
        estimated_price: 15,
      };
    },
  };
}
async function mount() {
  const hook = renderHook(useRide, { wrapper: RideProvider });
  await act(async () => {});
  return hook;
}
async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2500);
  });
}
beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe('ride lifecycle', () => {
  it('creates a passenger, books map coordinates and cancels', async () => {
    const { fetcher } = backend();
    const { result } = await mount();
    await act(() => result.current.createProfile('passenger', 'Ana'));
    await act(() => result.current.requestTrip(zones[0], zones[1]));
    expect(result.current.trips.passenger?.status).toBe('OFFERED');
    const booking = fetcher.mock.calls.find(
      ([url, options]) => url === '/api/trips' && options.method === 'POST',
    );
    expect(JSON.parse(String(booking?.[1].body))).toMatchObject({
      pickup: zones[0],
      dropoff: zones[1],
      rider_id: 'r1',
    });
    expect(booking?.[1].headers).toMatchObject({ 'X-Unter-Request': '1' });
    await act(() => result.current.cancel());
    expect(result.current.trips.passenger?.status).toBe('CANCELLED');
  });
  it('declines without retaining the offered trip, then accepts, picks up and completes', async () => {
    const mock = backend();
    const { result } = await mount();
    await act(() => result.current.createProfile('driver', 'Dan'));
    await act(() => result.current.goOnline());
    mock.incoming();
    await tick();
    await act(() => result.current.respond(false));
    expect(result.current.offer).toBeNull();
    expect(result.current.trips.driver).toBeUndefined();
    mock.incoming();
    await tick();
    await act(() => result.current.respond(true));
    expect(result.current.trips.driver?.status).toBe('ASSIGNED');
    await act(() => result.current.advance());
    expect(result.current.trips.driver?.status).toBe('PICKED_UP');
    await act(() => result.current.advance());
    expect(result.current.trips.driver?.status).toBe('COMPLETED');
    expect(result.current.earnings?.balance).toBe(18);
    await act(() => result.current.goOffline());
    expect(result.current.driver?.status).toBe('OFFLINE');
  });
  it('queues a mutation behind an in-flight poll instead of dropping it', async () => {
    const mock = backend();
    let release!: () => void;
    mock.delay(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );
    const hook = renderHook(useRide, { wrapper: RideProvider });
    await act(async () => {
      const pending = hook.result.current.createProfile('passenger', 'Ana');
      release();
      await pending;
    });
    expect(hook.result.current.session.profiles.passenger?.id).toBe('r1');
  });
  it('refreshes after a conflicting acceptance and displays the error', async () => {
    const mock = backend();
    const { result } = await mount();
    await act(() => result.current.createProfile('driver', 'Dan'));
    await act(() => result.current.goOnline());
    mock.incoming();
    await tick();
    mock.conflict();
    await act(() => result.current.respond(true));
    expect(result.current.message).toBe('Offer expired');
    expect(result.current.trips.driver).toBeUndefined();
  });
  it('does not send mutations offline and resumes polling after reconnecting', async () => {
    const { fetcher } = backend();
    const { result } = await mount();
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event('offline'));
    });
    const before = fetcher.mock.calls.length;
    await act(() => result.current.createProfile('passenger', 'Ana'));
    expect(fetcher.mock.calls.length).toBe(before);
    expect(result.current.online).toBe(false);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
    await act(async () => {
      window.dispatchEvent(new Event('online'));
    });
    expect(result.current.online).toBe(true);
  });
  it('keeps driver location fresh while a passenger profile also exists', async () => {
    const { fetcher } = backend();
    const { result } = await mount();
    await act(() => result.current.createProfile('driver', 'Dan'));
    await act(() => result.current.goOnline());
    await act(() => result.current.createProfile('passenger', 'Ana'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(
      fetcher.mock.calls.filter(([url]) => url.endsWith('/location')).length,
    ).toBeGreaterThanOrEqual(2);
  });
});
it('preserves the other tab’s profile and trip when saving a session', () => {
  saveSession({ profiles: { passenger: { id: 'r1', name: 'Ana' } }, tripIds: { passenger: 't1' } });
  saveSession({ profiles: { driver: { id: 'd1', name: 'Dan' } }, tripIds: { driver: 't2' } });
  const saved = JSON.parse(localStorage.getItem('unter-ride')!);
  expect(saved.profiles.passenger.id).toBe('r1');
  expect(saved.tripIds.passenger).toBe('t1');
});
