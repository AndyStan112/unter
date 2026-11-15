import type { Point, Role, Trip, TripStatus, Zone } from '../types/ride';
export const isTerminal = (trip: Trip | null) =>
  !trip || ['COMPLETED', 'CANCELLED', 'UNMATCHED'].includes(trip.status);
export const canCancel = (trip: Trip) => ['REQUESTED', 'OFFERED', 'ASSIGNED'].includes(trip.status);
const labels: Record<TripStatus, string> = {
  REQUESTED: 'Finding your driver',
  OFFERED: 'Waiting for a driver to accept',
  ASSIGNED: 'Your driver is on the way',
  PICKED_UP: 'Enjoy the ride',
  COMPLETED: 'You’ve arrived',
  CANCELLED: 'Ride cancelled',
  UNMATCHED: 'No driver available. Try again.',
};
export const tripLabel = (trip: Trip, role: Role) =>
  role === 'driver' && trip.status === 'ASSIGNED' ? 'Head to the pickup' : labels[trip.status];
export function pointLabel(point: Point, zones: Zone[]) {
  return (
    zones.find(
      (z) => Math.abs(z.lat - point.lat) < 0.00001 && Math.abs(z.lon - point.lon) < 0.00001,
    )?.name || `${point.lat.toFixed(4)}, ${point.lon.toFixed(4)}`
  );
}
export const samePoint = (a: Point, b: Point) => a.lat === b.lat && a.lon === b.lon;
