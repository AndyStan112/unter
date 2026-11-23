import { Box, ButtonBase, Stack, Typography } from '@mui/material';
import type { Point, Zone } from '../../types/ride';
import { pointLabel } from '../../services/rideState';
export const locationName = (point: Point | null, zones: Zone[], empty = 'Choose a place') =>
  !point
    ? empty
    : point.label ||
      (pointLabel(point, zones).includes(',') ? 'Pinned location' : pointLabel(point, zones));
export function RouteFields({
  pickup,
  dropoff,
  zones,
  onPickup,
  onDropoff,
  disabled = false,
}: {
  pickup: Point | null;
  dropoff: Point | null;
  zones: Zone[];
  onPickup?: () => void;
  onDropoff?: () => void;
  disabled?: boolean;
}) {
  return (
    <Stack sx={{ bgcolor: '#F4F5F7', borderRadius: '16px', overflow: 'hidden' }}>
      {[
        { point: pickup, label: 'Pickup', click: onPickup, round: true },
        { point: dropoff, label: 'Destination', click: onDropoff, round: false },
      ].map(({ point, label, click, round }) => (
        <ButtonBase
          key={label}
          aria-label={`Choose ${label.toLowerCase()}`}
          disabled={disabled || !click}
          onClick={click}
          sx={{
            justifyContent: 'flex-start',
            textAlign: 'left',
            px: 2,
            py: 1.25,
            minHeight: 56,
            gap: 2,
            '&.Mui-disabled': { color: 'text.primary' },
            '&:first-of-type': { borderBottom: '1px solid #E3E6EB' },
          }}
        >
          <Box
            sx={{
              width: 10,
              height: 10,
              bgcolor: round ? 'secondary.main' : 'primary.main',
              borderRadius: round ? '50%' : '2px',
              flexShrink: 0,
            }}
          />
          <Typography
            noWrap
            fontWeight={point ? 500 : 600}
            color={point ? 'text.primary' : 'text.secondary'}
          >
            {locationName(point, zones, round ? 'Your location' : 'Search destination')}
          </Typography>
        </ButtonBase>
      ))}
    </Stack>
  );
}
