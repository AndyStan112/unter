import { useEffect, useState } from 'react';
import {
  Avatar,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import DirectionsCarRounded from '@mui/icons-material/DirectionsCarRounded';
import CheckRounded from '@mui/icons-material/CheckRounded';
import { useRide } from '../../hooks/RideProvider';
import { canCancel, isTerminal, tripLabel } from '../../services/rideState';
import { RouteFields } from './RouteFields';
import { money } from './EarningsCard';
import type { Role } from '../../types/ride';
export function TripCard({ role, onDone }: { role: Role; onDone?: () => void }) {
  const { trips, offer, busy, online, zones, assignedDriver, respond, cancel, advance } = useRide();
  const [now, setNow] = useState(Date.now()),
    [confirmCancel, setConfirmCancel] = useState(false);
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
  const price = trip.price ?? incoming?.estimated_price;
  const waiting = ['REQUESTED', 'OFFERED'].includes(trip.status) && !incoming;
  const finished = isTerminal(trip);
  const bonus = role === 'driver' ? Number(trip.driver_bonus || 0) : 0;
  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
        <Typography variant="h3" component="h1">
          {incoming ? 'New request' : tripLabel(trip, role)}
        </Typography>
        {incoming && <Chip label={`${seconds}s`} color="primary" />}
        {trip.status === 'COMPLETED' && (
          <Avatar sx={{ bgcolor: '#EDF7F1', color: '#21854D', width: 36, height: 36 }}>
            <CheckRounded />
          </Avatar>
        )}
      </Stack>
      {waiting && <LinearProgress sx={{ borderRadius: 2 }} />}
      {role === 'passenger' && assignedDriver && !finished && (
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Avatar sx={{ bgcolor: '#EEF0F5', color: 'secondary.main' }}>
            {assignedDriver.name.charAt(0)}
          </Avatar>
          <Box>
            <Typography fontWeight={700}>{assignedDriver.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              Your driver
            </Typography>
          </Box>
          <DirectionsCarRounded sx={{ ml: 'auto !important', fontSize: 32 }} />
        </Stack>
      )}
      <RouteFields
        pickup={{ ...trip.pickup, label: trip.pickup_label || undefined }}
        dropoff={{ ...trip.dropoff, label: trip.dropoff_label || undefined }}
        zones={zones}
      />
      {price != null && (
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Box>
            <Typography variant="body2" color="text.secondary">
              {trip.status === 'COMPLETED' && role === 'driver'
                ? 'You earned'
                : incoming
                  ? 'Estimated fare'
                  : 'Fare'}
            </Typography>
            <Typography sx={{ fontSize: 28, fontWeight: 750, letterSpacing: '-.04em' }}>
              {money(Number(price) + (trip.status === 'COMPLETED' ? bonus : 0))}
            </Typography>
          </Box>
          <Chip label="Demo payment" size="small" variant="outlined" />
        </Stack>
      )}
      {bonus > 0 && (
        <Typography variant="body2" color="text.secondary">
          {money(bonus)} bonus {trip.status === 'COMPLETED' ? 'included' : 'on completion'}
        </Typography>
      )}
      {incoming ? (
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            color="inherit"
            disabled={busy || !online || !seconds}
            onClick={() => void respond(false)}
            sx={{ flex: 1 }}
          >
            Decline
          </Button>
          <Button
            variant="contained"
            disabled={busy || !online || !seconds}
            onClick={() => void respond(true)}
            sx={{ flex: 2 }}
          >
            {seconds ? 'Accept ride' : 'Offer expired'}
          </Button>
        </Stack>
      ) : role === 'passenger' && canCancel(trip) ? (
        <Button color="inherit" disabled={busy || !online} onClick={() => setConfirmCancel(true)}>
          Cancel ride
        </Button>
      ) : role === 'driver' && ['ASSIGNED', 'PICKED_UP'].includes(trip.status) ? (
        <Button
          variant="contained"
          fullWidth
          disabled={busy || !online}
          onClick={() => void advance()}
        >
          {trip.status === 'ASSIGNED' ? 'Confirm pickup' : 'Complete ride'}
        </Button>
      ) : finished && onDone ? (
        <Button variant="contained" fullWidth onClick={onDone}>
          Done
        </Button>
      ) : null}
      <Dialog open={confirmCancel} onClose={() => setConfirmCancel(false)}>
        <DialogTitle>Cancel this ride?</DialogTitle>
        <DialogActions>
          <Button onClick={() => setConfirmCancel(false)} color="inherit">
            Keep ride
          </Button>
          <Button
            color="error"
            onClick={() => {
              setConfirmCancel(false);
              void cancel();
            }}
          >
            Cancel ride
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
