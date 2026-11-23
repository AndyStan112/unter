import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded';
import MyLocationRounded from '@mui/icons-material/MyLocationRounded';
import { TripHistory } from '../../components/ride/TripHistory';
import { NotificationSettings } from '../../components/ride/NotificationSettings';
import { useRidePlan } from '../../hooks/useRidePlan';
import { money } from '../../components/ride/EarningsCard';
import { useRide } from '../../hooks/RideProvider';
import { isTerminal, samePoint } from '../../services/rideState';
import { RideMap } from '../../components/ride/RideMap';
import { LocationField } from '../../components/ride/LocationField';
import { ProfileForm } from '../../components/ride/ProfileForm';
import { TripCard } from '../../components/ride/TripCard';
import type { Point } from '../../types/ride';

export default function PassengerPage() {
  const { session, zones, trips, history, assignedDriver, online, busy, requestTrip } = useRide();
  const [pickup, setPickup] = useState<Point | null>(null),
    [dropoff, setDropoff] = useState<Point | null>(null);
  const [selecting, setSelecting] = useState<'pickup' | 'dropoff'>('pickup'),
    [locationError, setLocationError] = useState('');
  useEffect(() => {
    if (zones.length) {
      setPickup((p) => p || zones[0]);
      setDropoff((p) => p || zones[1] || zones[0]);
    }
  }, [zones]);
  const trip = trips.passenger,
    active = !!trip && !isTerminal(trip);
  const estimate = useRidePlan(active ? null : pickup, active ? null : dropoff);
  const freshDriver =
    assignedDriver?.position_updated_at &&
    Date.now() - Date.parse(assignedDriver.position_updated_at) < 120000
      ? assignedDriver.position
      : null;
  const selectPoint = (point: Point) => {
    if (selecting === 'pickup') {
      setPickup(point);
      setSelecting('dropoff');
    } else setDropoff(point);
  };
  const locate = () => {
    if (!navigator.geolocation) {
      setLocationError('Location unavailable. Select your pickup on the map.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPickup({ lat: position.coords.latitude, lon: position.coords.longitude });
        setLocationError('');
      },
      () => setLocationError('Location permission unavailable. Select your pickup on the map.'),
      { timeout: 10000 },
    );
  };
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: 'minmax(280px, 380px) minmax(0, 1fr)' },
        gap: 3,
        alignItems: 'start',
      }}
    >
      <Stack spacing={3}>
        {!session.profiles.passenger ? (
          <ProfileForm role="passenger" />
        ) : (
          <>
            {!active && (
              <Card>
                <CardContent sx={{ p: 3 }}>
                  <Stack
                    component="form"
                    spacing={2.5}
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (pickup && dropoff) void requestTrip(pickup, dropoff);
                    }}
                  >
                    <Stack spacing={0.5}>
                      <Typography variant="h3" component="h2">
                        Where to, {session.profiles.passenger.name}?
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Pick a zone or drop a pin on the map.
                      </Typography>
                    </Stack>
                    <LocationField
                      label="Pickup"
                      point={pickup}
                      zones={zones}
                      onChange={setPickup}
                      disabled={busy}
                    />
                    <LocationField
                      label="Destination"
                      point={dropoff}
                      zones={zones}
                      onChange={setDropoff}
                      disabled={busy}
                    />
                    <Button startIcon={<MyLocationRounded />} onClick={locate} disabled={busy}>
                      Use my location for pickup
                    </Button>
                    {locationError && <Alert severity="info">{locationError}</Alert>}
                    {pickup && dropoff && samePoint(pickup, dropoff) && (
                      <Alert severity="info">Choose a different destination.</Alert>
                    )}
                    {estimate.loading && <Typography>Calculating route and fare…</Typography>}
                    {estimate.plan && (
                      <Alert severity="info">
                        Estimated fare {money(estimate.plan.fare)} ·{' '}
                        {estimate.plan.route.source === 'road'
                          ? 'road distance'
                          : 'straight-line fallback'}
                        {estimate.plan.route.duration_seconds != null &&
                          ` · about ${Math.ceil(estimate.plan.route.duration_seconds / 60)} min`}
                        {estimate.plan.surge_multiplier > 1 &&
                          ` · ${estimate.plan.surge_multiplier}× surge`}
                      </Alert>
                    )}
                    {estimate.error && <Alert severity="info">{estimate.error}</Alert>}
                    <Button
                      type="submit"
                      variant="contained"
                      endIcon={<ArrowForwardRounded />}
                      disabled={
                        busy || !online || !pickup || !dropoff || samePoint(pickup, dropoff)
                      }
                    >
                      Request a ride
                    </Button>
                    <Typography variant="caption" color="text.secondary">
                      Your fare is fixed when a driver accepts. Payments are not collected in this
                      demo.
                    </Typography>
                  </Stack>
                </CardContent>
              </Card>
            )}
            <TripCard role="passenger" />
            {active && assignedDriver && !freshDriver && (
              <Alert severity="warning">
                Driver location is stale. Waiting for a fresh GPS update; pickup ETA is unavailable.
              </Alert>
            )}
            <NotificationSettings role="passenger" />
            <TripHistory trips={history.passenger || []} zones={zones} />
          </>
        )}
      </Stack>
      <Card>
        <CardContent sx={{ p: { xs: 2, md: 3 } }}>
          {!active && (
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              gap={1}
              flexWrap="wrap"
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">Choose on the map</Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={selecting}
                onChange={(_, value) => {
                  if (value) setSelecting(value);
                }}
                aria-label="Map selection mode"
              >
                <ToggleButton value="pickup">Pickup</ToggleButton>
                <ToggleButton value="dropoff">Destination</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
          )}
          <RideMap
            pickedUp={trip?.status === 'PICKED_UP'}
            pickup={active ? trip.pickup : pickup}
            dropoff={active ? trip.dropoff : dropoff}
            driver={active ? freshDriver : null}
            onSelect={!active && !busy ? selectPoint : undefined}
            instruction={
              active
                ? 'Your driver’s latest location appears on the map.'
                : `Tap the map to set your ${selecting === 'pickup' ? 'pickup' : 'destination'}.`
            }
          />
        </CardContent>
      </Card>
    </Box>
  );
}
