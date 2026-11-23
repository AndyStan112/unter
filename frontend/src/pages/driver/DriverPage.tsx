import { Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import MyLocationRounded from '@mui/icons-material/MyLocationRounded';
import { EarningsCard } from '../../components/ride/EarningsCard';
import { TripHistory } from '../../components/ride/TripHistory';
import { DriverPresence } from '../../components/ride/DriverPresence';
import { NotificationSettings } from '../../components/ride/NotificationSettings';
import { useRide } from '../../hooks/RideProvider';
import { isTerminal } from '../../services/rideState';
import { RideMap } from '../../components/ride/RideMap';
import { LocationField } from '../../components/ride/LocationField';
import { ProfileForm } from '../../components/ride/ProfileForm';
import { TripCard } from '../../components/ride/TripCard';
import { StatusChip } from '../../components/common/StatusChip';
export default function DriverPage() {
  const {
    session,
    earnings,
    history,
    zones,
    trips,
    offer,
    driver,
    driverPoint,
    busy,
    online,
    gpsEnabled,
    setDriverPoint,
    enableGps,
    goOnline,
    goOffline,
  } = useRide();
  const trip = offer?.trip || trips.driver,
    active = !!trip && !isTerminal(trip);
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
        {!session.profiles.driver ? (
          <ProfileForm role="driver" />
        ) : (
          <>
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Stack spacing={2.5}>
                  <Stack direction="row" justifyContent="space-between" gap={1} flexWrap="wrap">
                    <Typography variant="h3" component="h2">
                      Ready, {session.profiles.driver.name}?
                    </Typography>
                    {driver && <StatusChip label={driver.status} />}
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    Choose your location, then go online to receive nearby ride requests.
                  </Typography>
                  <LocationField
                    label="Your location"
                    point={driverPoint || driver?.position || zones[0] || null}
                    zones={zones}
                    onChange={setDriverPoint}
                    disabled={busy}
                  />
                  <Button startIcon={<MyLocationRounded />} onClick={enableGps} disabled={busy}>
                    {gpsEnabled ? 'Live GPS enabled' : 'Use live GPS'}
                  </Button>
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="contained"
                      disabled={busy || !online || !driver || driver.status !== 'OFFLINE'}
                      onClick={() => void goOnline()}
                    >
                      Go online
                    </Button>
                    <Button
                      variant="outlined"
                      disabled={
                        busy || !online || !driver || ['OFFLINE', 'ON_TRIP'].includes(driver.status)
                      }
                      onClick={() => void goOffline()}
                    >
                      Go offline
                    </Button>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    Keep the app open while online for location updates and incoming offers.
                    Selecting a point stops live GPS.
                  </Typography>
                </Stack>
              </CardContent>
            </Card>
            <TripCard role="driver" />
            <DriverPresence />
            <NotificationSettings role="driver" />
            <EarningsCard earnings={earnings} />
            <TripHistory trips={history.driver || []} zones={zones} />
          </>
        )}
      </Stack>
      <Card>
        <CardContent sx={{ p: { xs: 2, md: 3 } }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            Your city, your next ride
          </Typography>
          <RideMap
            pickedUp={trip?.status === 'PICKED_UP'}
            driver={driverPoint || driver?.position}
            pickup={active ? trip.pickup : null}
            dropoff={active ? trip.dropoff : null}
            onSelect={!busy ? setDriverPoint : undefined}
            instruction="Tap the map to update your location, or enable live GPS."
          />
        </CardContent>
      </Card>
    </Box>
  );
}
