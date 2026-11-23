import { useState } from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import EditLocationAltOutlined from '@mui/icons-material/EditLocationAltOutlined';
import { useRide } from '../../hooks/RideProvider';
import { isTerminal } from '../../services/rideState';
import { RideMap } from '../../components/ride/RideMap';
import { RideSheet } from '../../components/ride/RideSheet';
import { LocationPicker } from '../../components/ride/LocationPicker';
import { locationName } from '../../components/ride/RouteFields';
import { ProfileForm } from '../../components/ride/ProfileForm';
import { TripCard } from '../../components/ride/TripCard';
import { DriverPresence } from '../../components/ride/DriverPresence';
import { useRideChrome } from '../../components/ride/RideChrome';
import { money } from '../../components/ride/EarningsCard';
import type { Point } from '../../types/ride';
export default function DriverPage() {
  const {
    session,
    zones,
    trips,
    offer,
    driver,
    driverPoint,
    earnings,
    busy,
    online,
    setDriverPoint,
    enableGps,
    goOnline,
    goOffline,
  } = useRide();
  const { openPanel } = useRideChrome();
  const [editing, setEditing] = useState(false),
    [picking, setPicking] = useState(false),
    [draft, setDraft] = useState<Point | null>(null),
    [dismissed, setDismissed] = useState<string | null>(null);
  const trip = offer?.trip || trips.driver,
    active = !!trip && !isTerminal(trip);
  const showTrip = !!trip && (active || trip.id !== dismissed);
  const position = driverPoint || driver?.position || zones[0] || null;
  const available = driver && driver.status !== 'OFFLINE';
  return (
    <>
      <RideMap
        pickedUp={trip?.status === 'PICKED_UP'}
        driver={position}
        pickup={active ? trip.pickup : null}
        dropoff={active ? trip.dropoff : null}
        picking={picking}
        pickPoint={draft}
        onSelect={picking ? setDraft : undefined}
        onLocate={enableGps}
        extraControl={<DriverPresence />}
      />
      <RideSheet label="Driver controls">
        {picking ? (
          <Stack spacing={2}>
            <Typography variant="h3" component="h1">
              Set your location
            </Typography>
            <Typography color="text.secondary">Move the map to place your pin.</Typography>
            <Stack direction="row" spacing={1}>
              <Button color="inherit" onClick={() => setPicking(false)} sx={{ flex: 1 }}>
                Back
              </Button>
              <Button
                variant="contained"
                sx={{ flex: 2 }}
                disabled={!draft}
                onClick={() => {
                  if (draft) setDriverPoint({ ...draft, label: 'Pinned location' });
                  setPicking(false);
                }}
              >
                Confirm location
              </Button>
            </Stack>
          </Stack>
        ) : !session.profiles.driver ? (
          <ProfileForm role="driver" />
        ) : showTrip ? (
          <TripCard role="driver" onDone={() => setDismissed(trip.id)} />
        ) : (
          <Stack spacing={2}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Box
                sx={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  bgcolor: available ? '#21854D' : '#9BA3A8',
                }}
              />
              <Typography variant="h3" component="h1">
                {available ? 'You’re online' : 'Ready to drive?'}
              </Typography>
            </Stack>
            <Typography color="text.secondary">
              {available ? 'Looking for nearby requests' : 'Go online to start receiving rides'}
            </Typography>
            <Button
              color="inherit"
              startIcon={<EditLocationAltOutlined />}
              onClick={() => setEditing(true)}
              disabled={busy}
              sx={{ justifyContent: 'flex-start', bgcolor: '#F4F5F7', px: 2 }}
            >
              {locationName(position, zones, 'Set your location')}
            </Button>
            <Button
              variant="contained"
              fullWidth
              disabled={busy || !online || !driver || driver.status === 'ON_TRIP'}
              onClick={() => void (available ? goOffline() : goOnline())}
            >
              {available ? 'Go offline' : 'Go online'}
            </Button>
            {earnings && (
              <Button
                color="inherit"
                onClick={() => openPanel('earnings')}
                sx={{ justifyContent: 'space-between', py: 0.5, minHeight: 36 }}
              >
                <Typography variant="body2" color="text.secondary">
                  Today’s earnings
                </Typography>
                <Typography fontWeight={700}>{money(earnings.today)}</Typography>
              </Button>
            )}
          </Stack>
        )}
      </RideSheet>
      <LocationPicker
        open={editing}
        label="Your location"
        zones={zones}
        onClose={() => setEditing(false)}
        onSelect={(point) => {
          setDriverPoint(point);
          setEditing(false);
        }}
        onLocate={() => {
          enableGps();
          setEditing(false);
        }}
        onMap={() => {
          setDraft(position);
          setPicking(true);
          setEditing(false);
        }}
      />
    </>
  );
}
