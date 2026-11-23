import { useEffect, useState } from 'react';
import { Alert, Button, Stack, Typography } from '@mui/material';
import { api, errorMessage } from '../../services/api';
import { buildAsset } from '../../services/buildAsset';
import { useRide } from '../../hooks/RideProvider';
import type { Role } from '../../types/ride';
export function NotificationSettings({ role }: { role: Role }) {
  const { session, online } = useRide();
  const profile = session.profiles[role];
  const [enabled, setEnabled] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const supported =
    'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
  useEffect(() => {
    let active = true;
    if (supported)
      navigator.serviceWorker
        .getRegistration('/ride/')
        .then(async (registration) => {
          const subscription = await registration?.pushManager.getSubscription();
          if (active)
            setEnabled(
              !!subscription &&
                localStorage.getItem('unter-push-profile') === `${role}:${profile?.id}`,
            );
        })
        .catch(() => {});
    return () => {
      active = false;
    };
  }, [role, profile?.id, supported]);
  if (!profile) return null;
  async function toggle() {
    if (!profile) return;
    setBusy(true);
    setError('');
    try {
      if (!import.meta.env.PROD)
        throw new Error('Push notifications require the built PWA on HTTPS or localhost.');
      if (!enabled && (await Notification.requestPermission()) !== 'granted')
        throw new Error('Notifications are blocked. Enable them in your browser settings.');
      await navigator.serviceWorker.register(buildAsset('/ride/sw.js'), {
        scope: '/ride/',
        updateViaCache: 'none',
      });
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (enabled) {
        if (subscription) {
          await api('push-unsubscribe', 'POST', { endpoint: subscription.endpoint });
          await subscription.unsubscribe();
        }
        localStorage.removeItem('unter-push-profile');
        setEnabled(false);
      } else {
        const { public_key: publicKey } = await api<{ public_key: string }>('push-key');
        const decoded = atob(
          publicKey.replace(/-/g, '+').replace(/_/g, '/') +
            '='.repeat((4 - (publicKey.length % 4)) % 4),
        );
        const applicationServerKey = Uint8Array.from(decoded, (character) =>
          character.charCodeAt(0),
        );
        subscription ||= await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey,
        });
        await api('push-subscriptions', 'POST', {
          role,
          profile_id: profile.id,
          subscription: subscription.toJSON(),
        });
        localStorage.setItem('unter-push-profile', `${role}:${profile.id}`);
        setEnabled(true);
      }
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Stack spacing={1}>
      <Button
        variant="outlined"
        disabled={!supported || !online || busy}
        onClick={() => void toggle()}
      >
        {busy
          ? 'Updating notifications…'
          : enabled
            ? `Disable ${role} notifications`
            : `Enable ${role} notifications`}
      </Button>
      <Typography variant="caption" color="text.secondary">
        Ride updates can arrive while the app is closed. On iPhone, install Unter first. This device
        receives alerts for the profile you enable.
      </Typography>
      {!supported && (
        <Alert severity="info">
          Push notifications are unavailable in this browser. Keep Unter open for ride updates.
        </Alert>
      )}
      {error && <Alert severity="info">{error}</Alert>}
    </Stack>
  );
}
