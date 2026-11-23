import { useEffect, useState } from 'react';
import { Alert, Box, Button, Chip, Stack, Typography } from '@mui/material';
import DirectionsCarRounded from '@mui/icons-material/DirectionsCarRounded';
import { useRide } from '../../hooks/RideProvider';
import { useRidePlan } from '../../hooks/useRidePlan';
import { isTerminal, samePoint } from '../../services/rideState';
import { RideMap } from '../../components/ride/RideMap';
import { RideSheet } from '../../components/ride/RideSheet';
import { LocationPicker } from '../../components/ride/LocationPicker';
import { RouteFields } from '../../components/ride/RouteFields';
import { ProfileForm } from '../../components/ride/ProfileForm';
import { TripCard } from '../../components/ride/TripCard';
import { money } from '../../components/ride/EarningsCard';
import type { Point } from '../../types/ride';
export default function PassengerPage() {
  const { session, zones, trips, assignedDriver, online, busy, requestTrip } = useRide();
  const [pickup, setPickup] = useState<Point | null>(null),
    [dropoff, setDropoff] = useState<Point | null>(null);
  const [editing, setEditing] = useState<'pickup' | 'dropoff' | null>(null),
    [picking, setPicking] = useState<'pickup' | 'dropoff' | null>(null);
  const [draft, setDraft] = useState<Point | null>(null),
    [locationError, setLocationError] = useState(''),
    [dismissed, setDismissed] = useState<string | null>(null);
  useEffect(() => {
    if (zones.length) setPickup((point) => point || zones[0]);
  }, [zones]);
  const trip = trips.passenger,
    active = !!trip && !isTerminal(trip);
  const showTrip = !!trip && (active || trip.id !== dismissed);
  const estimate = useRidePlan(active || !session.profiles.passenger ? null : pickup, dropoff);
  const freshDriver =
    assignedDriver?.position_updated_at &&
    Date.now() - Date.parse(assignedDriver.position_updated_at) < 120000
      ? assignedDriver.position
      : null;
  const choose = (point: Point) => {
    if (editing === 'dropoff') setDropoff(point);
    else setPickup(point);
    setEditing(null);
    setLocationError('');
  };
  const locate = () => {
    if (!navigator.geolocation) {
      setLocationError('Choose your pickup on the map.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPickup({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          label: 'Current location',
        });
        setLocationError('');
        setEditing(null);
      },
      () => setLocationError('Allow location access or choose a pickup.'),
      { timeout: 10000 },
    );
  };
  return (
    <>
      <RideMap
        pickedUp={trip?.status === 'PICKED_UP'}
        pickup={active ? trip.pickup : pickup}
        dropoff={active ? trip.dropoff : dropoff}
        driver={active ? freshDriver : null}
        picking={!!picking}
        pickPoint={draft}
        onSelect={picking ? setDraft : undefined}
        onLocate={active ? undefined : locate}
      />
      <RideSheet label="Book a ride">
        {picking ? (
          <Stack spacing={2}>
            <Typography variant="h3" component="h1">
              {picking === 'pickup' ? 'Set pickup' : 'Set destination'}
            </Typography>
            <Typography color="text.secondary">Move the map to place your pin.</Typography>
            <Stack direction="row" spacing={1}>
              <Button color="inherit" onClick={() => setPicking(null)} sx={{ flex: 1 }}>
                Back
              </Button>
              <Button
                variant="contained"
                disabled={!draft}
                onClick={() => {
                  if (draft)
                    (picking === 'pickup' ? setPickup : setDropoff)({
                      ...draft,
                      label: 'Pinned location',
                    });
                  setPicking(null);
                }}
                sx={{ flex: 2 }}
              >
                Confirm location
              </Button>
            </Stack>
          </Stack>
        ) : !session.profiles.passenger ? (
          <ProfileForm role="passenger" />
        ) : showTrip ? (
          <TripCard role="passenger" onDone={() => setDismissed(trip.id)} />
        ) : (
          <Stack spacing={2}>
            <Typography variant="h3" component="h1">
              Where to?
            </Typography>
            <RouteFields
              pickup={pickup}
              dropoff={dropoff}
              zones={zones}
              disabled={busy}
              onPickup={() => setEditing('pickup')}
              onDropoff={() => setEditing('dropoff')}
            />
            {pickup && dropoff && samePoint(pickup, dropoff) && (
              <Alert severity="info">Choose a different destination.</Alert>
            )}
            {dropoff && (
              <Stack
                direction="row"
                alignItems="center"
                spacing={1.5}
                sx={{ border: '1.5px solid #182529', borderRadius: '16px', px: 1.5, py: 1.25 }}
              >
                <DirectionsCarRounded sx={{ fontSize: 38, mr: 0.5 }} />
                <Box sx={{ flex: 1 }}>
                  <Typography fontWeight={750}>Unter</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {estimate.plan?.route.duration_seconds != null
                      ? `${Math.max(1, Math.ceil(estimate.plan.route.duration_seconds / 60))} min trip`
                      : 'Standard ride'}
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography fontWeight={750}>
                    {estimate.plan ? money(estimate.plan.fare) : estimate.loading ? '…' : '—'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Estimated fare
                  </Typography>
                </Box>
              </Stack>
            )}
            {locationError && (
              <Alert severity="info" onClose={() => setLocationError('')}>
                {locationError}
              </Alert>
            )}
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Chip label="Demo payment" size="small" variant="outlined" />
              {estimate.plan && estimate.plan.surge_multiplier > 1 && (
                <Typography variant="body2" color="text.secondary">
                  Busy area · {estimate.plan.surge_multiplier}×
                </Typography>
              )}
            </Stack>
            <Button
              fullWidth
              variant="contained"
              disabled={busy || !online || !pickup || !dropoff || samePoint(pickup, dropoff)}
              onClick={() => {
                if (pickup && dropoff) void requestTrip(pickup, dropoff);
              }}
            >
              Request a ride
            </Button>
          </Stack>
        )}
        {active && assignedDriver && !freshDriver && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Updating your driver’s location…
          </Typography>
        )}
      </RideSheet>
      <LocationPicker
        open={!!editing}
        label={editing === 'pickup' ? 'Pickup' : 'Destination'}
        zones={zones}
        onClose={() => setEditing(null)}
        onSelect={choose}
        onLocate={editing === 'pickup' ? locate : undefined}
        onMap={() => {
          setDraft((editing === 'pickup' ? pickup : dropoff) || pickup || zones[0] || null);
          setPicking(editing);
          setEditing(null);
        }}
      />
    </>
  );
}
