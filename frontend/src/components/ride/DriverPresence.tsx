import { useEffect, useState } from 'react';
import { Alert, Button, Stack } from '@mui/material';
import { useRide } from '../../hooks/RideProvider';
export function DriverPresence() {
  const { driver, gpsEnabled } = useRide();
  const [awake, setAwake] = useState(false),
    [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const active = !!driver && driver.status !== 'OFFLINE';
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let lock: WakeLockSentinel | null = null,
      cancelled = false;
    const acquire = async () => {
      if (document.visibilityState !== 'visible' || !awake || !active) return;
      try {
        const next = await navigator.wakeLock.request('screen');
        if (cancelled) {
          await next.release();
          return;
        }
        lock = next;
      } catch {
        setError('Keep-awake unavailable. Keep the app visible while driving.');
        setAwake(false);
      }
    };
    if (awake && active) void acquire();
    document.addEventListener('visibilitychange', acquire);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', acquire);
      void lock?.release();
    };
  }, [awake, active]);
  if (!active) return null;
  const stale = !driver.position_updated_at || now - Date.parse(driver.position_updated_at) > 60000;
  return (
    <Stack spacing={1}>
      <Alert severity={stale ? 'warning' : 'info'}>
        {stale
          ? 'Location is stale. Send a fresh GPS update to stay eligible for matching.'
          : gpsEnabled
            ? 'Live GPS is updating while the app is active.'
            : 'Using your selected map location. Enable GPS to follow your movement.'}{' '}
        Keep Unter visible while driving. Background GPS can be suspended by your phone.
      </Alert>
      {'wakeLock' in navigator && (
        <Button
          variant="outlined"
          onClick={() => {
            setError('');
            setAwake(!awake);
          }}
        >
          {awake ? 'Allow screen sleep' : 'Keep screen awake'}
        </Button>
      )}
      {error && <Alert severity="info">{error}</Alert>}
    </Stack>
  );
}
