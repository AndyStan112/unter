import { useEffect, useRef, useState } from 'react';
import { ridePlan } from '../services/ridePlanning';
import type { Point, RidePlan } from '../types/ride';
export function useRidePlan(start?: Point | null, end?: Point | null, moving = false) {
  const lastRequest = useRef(0);
  const [plan, setPlan] = useState<RidePlan | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const a = start?.lat,
    b = start?.lon,
    c = end?.lat,
    d = end?.lon;
  useEffect(() => {
    let active = true;
    setPlan(null);
    setError('');
    if (a == null || b == null || c == null || d == null || !navigator.onLine) {
      setLoading(false);
      return;
    }
    const fetchPlan = () => {
      lastRequest.current = Date.now();
      setLoading(true);
      ridePlan({ lat: a, lon: b }, { lat: c, lon: d })
        .then((value) => {
          if (active) {
            setPlan(value);
            setError('');
          }
        })
        .catch(() => {
          if (active) {
            setPlan(null);
            setError('Route unavailable. You can still choose map pins.');
          }
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    };
    const timer = window.setTimeout(
      fetchPlan,
      moving ? Math.max(350, 10000 - (Date.now() - lastRequest.current)) : 350,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [a, b, c, d, moving]);
  return { plan, error, loading };
}
