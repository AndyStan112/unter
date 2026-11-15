import { useEffect, useState } from 'react';
import { Button, Card, CardContent, Divider, Stack, Typography } from '@mui/material';
import { useRide } from '../../hooks/RideProvider';
import { canCancel, pointLabel, tripLabel } from '../../services/rideState';
import { StatusChip } from '../common/StatusChip';
import type { Role } from '../../types/ride';
export function TripCard({ role }: { role: Role }) {
  const { trips, offer, busy, online, zones, assignedDriver, respond, cancel, advance } = useRide();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const incoming = role === 'driver' ? offer : null;
  const trip = incoming?.trip || trips[role];
  if (!trip) return null;
  const seconds = incoming
    ? Math.max(0, Math.ceil((Date.parse(incoming.offer.expires_at) - now) / 1000))
    : 0;
  const disabled = busy || !online;
  const price = trip.price ?? incoming?.estimated_price;
  return (
    <Card>
      <CardContent sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            gap={1}
            flexWrap="wrap"
          >
            <Typography variant="overline" color="primary">
              {incoming ? 'Incoming request' : 'Your ride'}
            </Typography>
            <StatusChip label={incoming ? `${seconds}s to respond` : trip.status} />
          </Stack>
          <Typography variant="h3" component="h2">
            {incoming ? 'A passenger needs a ride' : tripLabel(trip, role)}
          </Typography>
          <Typography color="text.secondary">
            {pointLabel(trip.pickup, zones)} → {pointLabel(trip.dropoff, zones)}
          </Typography>
          <Typography variant="h4">
            {price == null
              ? 'Fare confirmed on acceptance'
              : `${Number(price).toFixed(2)} RON${incoming ? ' · estimated' : ''}`}
          </Typography>
          {role === 'passenger' && assignedDriver && (
            <Typography variant="body2">Your driver · {assignedDriver.name}</Typography>
          )}
          <Divider />
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {incoming ? (
              <>
                <Button
                  variant="contained"
                  disabled={disabled || seconds === 0}
                  onClick={() => void respond(true)}
                >
                  {seconds ? 'Accept ride' : 'Offer expired'}
                </Button>
                <Button
                  variant="outlined"
                  disabled={disabled || seconds === 0}
                  onClick={() => void respond(false)}
                >
                  Decline
                </Button>
              </>
            ) : role === 'passenger' && canCancel(trip) ? (
              <Button variant="outlined" disabled={disabled} onClick={() => void cancel()}>
                Cancel ride
              </Button>
            ) : role === 'driver' && ['ASSIGNED', 'PICKED_UP'].includes(trip.status) ? (
              <Button variant="contained" disabled={disabled} onClick={() => void advance()}>
                {trip.status === 'ASSIGNED' ? 'Confirm pickup' : 'Complete ride'}
              </Button>
            ) : null}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
