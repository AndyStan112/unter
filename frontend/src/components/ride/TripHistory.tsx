import { Card, CardContent, Stack, Typography } from '@mui/material';
import { pointLabel } from '../../services/rideState';
import { StatusChip } from '../common/StatusChip';
import { money } from './EarningsCard';
import type { Trip, Zone } from '../../types/ride';
export function TripHistory({ trips, zones }: { trips: Trip[]; zones: Zone[] }) {
  return (
    <Card>
      <CardContent sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h5" component="h2">
            Recent rides
          </Typography>
          {!trips.length && (
            <Typography color="text.secondary">Your rides will appear here.</Typography>
          )}
          {trips.map((trip) => (
            <Stack key={trip.id} spacing={0.5}>
              <Stack direction="row" justifyContent="space-between" gap={1}>
                <Typography>
                  {trip.pickup_label || pointLabel(trip.pickup, zones)} to{' '}
                  {trip.dropoff_label || pointLabel(trip.dropoff, zones)}
                </Typography>
                <StatusChip label={trip.status} />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {trip.requested_at && new Date(trip.requested_at).toLocaleString()}
                {trip.status === 'COMPLETED' && trip.price != null
                  ? ` · ${money(trip.price)} · mock paid`
                  : ''}
                {trip.status === 'CANCELLED' || trip.status === 'UNMATCHED' ? ' · no charge' : ''}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
