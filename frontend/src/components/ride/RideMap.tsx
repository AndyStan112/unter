import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Alert, Box, Stack, Typography, useTheme } from '@mui/material';
import type { Point } from '../../types/ride';

interface Props {
  pickup?: Point | null;
  dropoff?: Point | null;
  driver?: Point | null;
  onSelect?: (point: Point) => void;
  instruction?: string;
}
const center: L.LatLngTuple = [45.7537, 21.2257];
const latLng = (p: Point): L.LatLngTuple => [p.lat, p.lon];
export function RideMap({ pickup, dropoff, driver, onSelect, instruction }: Props) {
  const element = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null);
  const selection = useRef(onSelect),
    layers = useRef<L.LayerGroup | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const theme = useTheme();
  selection.current = onSelect;
  const framing = useRef('');
  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { center, zoom: 13, scrollWheelZoom: false });
    map.current = instance;
    layers.current = L.layerGroup().addTo(instance);
    const tiles = L.tileLayer(
      import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      },
    ).addTo(instance);
    tiles.on('tileerror', () => setUnavailable(true));
    tiles.on('tileload', () => setUnavailable(false));
    instance.on('click', (event) =>
      selection.current?.({ lat: event.latlng.lat, lon: event.latlng.lng }),
    );
    const resize = new ResizeObserver(() => instance.invalidateSize());
    resize.observe(element.current);
    return () => {
      resize.disconnect();
      instance.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const instance = map.current,
      group = layers.current;
    if (!instance || !group) return;
    group.clearLayers();
    const markers = [
      { point: pickup, color: theme.palette.primary.main, label: 'Pickup' },
      { point: dropoff, color: theme.palette.secondary.main, label: 'Destination' },
      { point: driver, color: theme.palette.text.primary, label: 'Driver' },
    ];
    markers.forEach(({ point, color, label }) => {
      if (point)
        L.circleMarker(latLng(point), {
          radius: 9,
          color: '#fff',
          weight: 3,
          fillColor: color,
          fillOpacity: 1,
        })
          .bindTooltip(label, { permanent: true, direction: 'top', offset: [0, -10] })
          .addTo(group);
    });
    if (pickup && dropoff)
      L.polyline([latLng(pickup), latLng(dropoff)], {
        color: theme.palette.secondary.main,
        weight: 4,
        dashArray: '8 8',
      }).addTo(group);
    if (driver && pickup)
      L.polyline([latLng(driver), latLng(pickup)], {
        color: theme.palette.primary.main,
        weight: 3,
        dashArray: '4 8',
      }).addTo(group);
    // Reframe for selected endpoints, but don't interrupt panning on every driver update.
    const key = JSON.stringify([pickup, dropoff]);
    const points = markers.flatMap((m) => (m.point ? [latLng(m.point)] : []));
    if (points.length && framing.current !== key) {
      framing.current = key;
      if (points.length > 1)
        instance.fitBounds(L.latLngBounds(points), { padding: [55, 55], maxZoom: 15 });
      else instance.setView(points[0], 14);
    }
  }, [pickup, dropoff, driver, theme]);
  return (
    <Stack spacing={1.5}>
      {instruction && (
        <Typography variant="body2" color="text.secondary">
          {instruction}
        </Typography>
      )}
      <Box
        sx={{
          position: 'relative',
          height: { xs: 330, md: 470 },
          borderRadius: 3,
          overflow: 'hidden',
          border: 1,
          borderColor: 'divider',
          bgcolor: 'grey.100',
        }}
      >
        <Box
          ref={element}
          role="region"
          aria-label="Interactive ride map"
          sx={{ height: '100%' }}
        />
        {unavailable && (
          <Alert
            severity="info"
            sx={{ position: 'absolute', top: 12, left: 48, right: 12, zIndex: 500 }}
          >
            Map tiles unavailable. You can still use the location fields.
          </Alert>
        )}
      </Box>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        {[
          ['Pickup', 'primary.main'],
          ['Destination', 'secondary.main'],
          ['Driver', 'text.primary'],
        ].map(([label, color]) => (
          <Stack key={label} direction="row" alignItems="center" spacing={0.75}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color }} />
            <Typography variant="caption" color="text.secondary">
              {label}
            </Typography>
          </Stack>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Dotted lines connect the points; they are not road directions. Map tiles need an internet
        connection.
      </Typography>
    </Stack>
  );
}
