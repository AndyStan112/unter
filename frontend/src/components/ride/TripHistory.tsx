import { Box, Divider, Stack, Typography } from '@mui/material';
import DirectionsCarOutlined from '@mui/icons-material/DirectionsCarOutlined';
import { locationName } from './RouteFields';
import { money } from './EarningsCard';
import type { Trip, Zone } from '../../types/ride';
const statuses: Record<string, string> = {
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  UNMATCHED: 'No driver found',
  ASSIGNED: 'Driver on the way',
  REQUESTED: 'Finding a driver',
  OFFERED: 'Finding a driver',
  PICKED_UP: 'In progress',
};
export function TripHistory({ trips, zones }: { trips: Trip[]; zones: Zone[] }) {
  return (
    <Stack spacing={2.5}>
      {!trips.length && <Typography color="text.secondary">No rides yet.</Typography>}
      {trips.map((trip) => (
        <Box key={trip.id}>
          <Stack direction="row" spacing={1.5} alignItems="flex-start">
            <Box sx={{ bgcolor: '#F4F5F7', p: 1.5, borderRadius: 3 }}>
              <DirectionsCarOutlined />
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography fontWeight={600} noWrap>
                {locationName({ ...trip.dropoff, label: trip.dropoff_label || undefined }, zones)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {trip.requested_at &&
                  new Date(trip.requested_at).toLocaleDateString(undefined, {
                    day: 'numeric',
                    month: 'short',
                  })}{' '}
                · {statuses[trip.status]}
              </Typography>
            </Box>
            {trip.price != null && trip.status === 'COMPLETED' && (
              <Typography fontWeight={600} sx={{ whiteSpace: 'nowrap' }}>
                {money(trip.price)}
              </Typography>
            )}
          </Stack>
          <Divider sx={{ mt: 2 }} />
        </Box>
      ))}
    </Stack>
  );
}
