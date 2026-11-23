import { MenuItem, TextField } from '@mui/material';
import { AddressSearch } from './AddressSearch';
import { Stack } from '@mui/material';
import { pointLabel } from '../../services/rideState';
import type { Point, Zone } from '../../types/ride';
export function LocationField({
  label,
  point,
  zones,
  onChange,
  disabled = false,
}: {
  label: string;
  point: Point | null;
  zones: Zone[];
  onChange: (point: Point) => void;
  disabled?: boolean;
}) {
  const match =
    point &&
    zones.findIndex(
      (z) => Math.abs(z.lat - point.lat) < 0.00001 && Math.abs(z.lon - point.lon) < 0.00001,
    );
  const value = point ? (match !== null && match >= 0 ? String(match) : 'custom') : '';
  return (
    <Stack spacing={1}>
      <TextField
        select
        fullWidth
        label={label}
        value={value}
        disabled={disabled || !zones.length}
        onChange={(e) => {
          const zone = zones[Number(e.target.value)];
          if (zone) onChange({ lat: zone.lat, lon: zone.lon });
        }}
      >
        {point && value === 'custom' && (
          <MenuItem value="custom">
            {point.label || `Map pin · ${pointLabel(point, zones)}`}
          </MenuItem>
        )}
        {zones.map((z, i) => (
          <MenuItem key={z.name} value={String(i)}>
            {z.name}
          </MenuItem>
        ))}
      </TextField>
      <AddressSearch label={label} onSelect={onChange} disabled={disabled} />
    </Stack>
  );
}
