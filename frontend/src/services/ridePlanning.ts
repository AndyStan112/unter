import { api } from './api';
import type { Point, RidePlan } from '../types/ride';
const cache = new Map<string, { at: number; value: Promise<RidePlan> }>();
export function ridePlan(pickup: Point, dropoff: Point): Promise<RidePlan> {
  const key = [pickup.lat, pickup.lon, dropoff.lat, dropoff.lon].map((n) => n.toFixed(4)).join(',');
  const saved = cache.get(key);
  if (saved && Date.now() - saved.at < 30000) return saved.value;
  const value = api<RidePlan>('ride-plan', 'POST', { pickup, dropoff });
  cache.set(key, { at: Date.now(), value });
  if (cache.size > 64) cache.delete(cache.keys().next().value!);
  value.catch(() => cache.delete(key));
  return value;
}
