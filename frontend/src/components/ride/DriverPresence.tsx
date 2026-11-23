import { useEffect, useState } from 'react';
import { IconButton, Snackbar, Alert } from '@mui/material';
import ScreenLockPortraitRounded from '@mui/icons-material/ScreenLockPortraitRounded';
import { useRide } from '../../hooks/RideProvider';
export function DriverPresence() {
  const { driver } = useRide();
  const [awake, setAwake] = useState(false),
    [error, setError] = useState('');
  const active = !!driver && driver.status !== 'OFFLINE';
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
        setError('Keep the app open while driving.');
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
  if (!active || !('wakeLock' in navigator)) return null;
  return (
    <>
      <IconButton
        aria-label="Keep screen on"
        aria-pressed={awake}
        onClick={() => setAwake(!awake)}
        sx={{
          bgcolor: awake ? 'primary.main' : 'white',
          color: awake ? 'white' : 'text.primary',
          width: 48,
          height: 48,
          boxShadow: '0 2px 12px #17244422',
          '&:hover': { bgcolor: awake ? 'primary.main' : '#F5F6F8' },
        }}
      >
        <ScreenLockPortraitRounded />
      </IconButton>
      <Snackbar open={!!error} autoHideDuration={5000} onClose={() => setError('')}>
        <Alert severity="info">{error}</Alert>
      </Snackbar>
    </>
  );
}
