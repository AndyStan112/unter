import { useEffect, useRef, useState, type ReactNode } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import MyLocationRounded from '@mui/icons-material/MyLocationRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import NavigationRounded from '@mui/icons-material/NavigationRounded';
import PlaceRounded from '@mui/icons-material/PlaceRounded';
import { useRidePlan } from '../../hooks/useRidePlan';
import { useRideChrome } from './RideChrome';
import type { Point } from '../../types/ride';

interface Props {
  pickedUp?: boolean;
  pickup?: Point | null;
  dropoff?: Point | null;
  driver?: Point | null;
  onSelect?: (point: Point) => void;
  onLocate?: () => void;
  picking?: boolean;
  pickPoint?: Point | null;
  extraControl?: ReactNode;
}
const center: L.LatLngTuple = [45.7537, 21.2257];
const latLng = (point: Point): L.LatLngTuple => [point.lat, point.lon];
export function RideMap({
  pickup,
  dropoff,
  driver,
  onSelect,
  onLocate,
  picking = false,
  pickPoint,
  pickedUp = false,
  extraControl,
}: Props) {
  const element = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null);
  const selection = useRef(onSelect),
    selecting = useRef(picking),
    layers = useRef<L.LayerGroup | null>(null);
  const pickAnchor = useRef(pickPoint);
  pickAnchor.current = pickPoint;
  const fit = useRef(() => {}),
    framing = useRef('');
  const [unavailable, setUnavailable] = useState(false),
    [directions, setDirections] = useState(false);
  const theme = useTheme(),
    desktop = useMediaQuery('(min-width:900px), (min-width:600px) and (max-height:500px)');
  const { sheetHeight } = useRideChrome();
  const journey = useRidePlan(picking ? null : pickup, picking ? null : dropoff);
  const target = pickedUp ? dropoff : pickup;
  const approach = useRidePlan(picking ? null : driver, picking ? null : target, true);
  const guidance = approach.plan?.route || journey.plan?.route;
  selection.current = onSelect;
  selecting.current = picking;
  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, {
      center,
      zoom: 14,
      zoomControl: false,
      scrollWheelZoom: true,
    });
    instance.attributionControl.setPrefix('');
    map.current = instance;
    layers.current = L.layerGroup().addTo(instance);
    const tiles = L.tileLayer(
      import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      },
    ).addTo(instance);
    tiles.on('tileerror', () => setUnavailable(true));
    tiles.on('tileload', () => setUnavailable(false));
    instance.on('click', (event) => {
      if (selecting.current) {
        instance.panTo(event.latlng);
        selection.current?.({ lat: event.latlng.lat, lon: event.latlng.lng });
      }
    });
    instance.on('moveend', () => {
      if (selecting.current) {
        const point = instance.getCenter();
        selection.current?.({ lat: point.lat, lon: point.lng });
      }
    });
    const observer = new ResizeObserver(() => {
      instance.invalidateSize({ pan: false });
      fit.current();
    });
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      instance.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!picking || !instance) return;
    if (pickAnchor.current) instance.panTo(latLng(pickAnchor.current), { animate: false });
    const point = instance.getCenter();
    selection.current?.({ lat: point.lat, lon: point.lng });
  }, [picking]);
  useEffect(() => {
    const instance = map.current,
      group = layers.current;
    if (!instance || !group) return;
    group.clearLayers();
    const markers = [
      { point: pickup, color: theme.palette.secondary.main, label: 'Pickup' },
      { point: dropoff, color: theme.palette.primary.main, label: 'Destination' },
      { point: driver, color: '#172444', label: 'Driver' },
    ];
    if (!picking) {
      markers.forEach(({ point, color, label }) => {
        if (point)
          L.circleMarker(latLng(point), {
            radius: label === 'Driver' ? 10 : 7,
            color: '#fff',
            weight: 3,
            fillColor: color,
            fillOpacity: 1,
          })
            .bindTooltip(label)
            .addTo(group);
      });
      if (pickup && dropoff)
        L.polyline(journey.plan?.route.geometry.map(latLng) || [latLng(pickup), latLng(dropoff)], {
          color: theme.palette.secondary.main,
          weight: 5,
          opacity: 0.8,
          dashArray: journey.plan?.route.source === 'road' ? undefined : '6 9',
        }).addTo(group);
      if (driver && target)
        L.polyline(approach.plan?.route.geometry.map(latLng) || [latLng(driver), latLng(target)], {
          color: '#172444',
          weight: 5,
          dashArray: approach.plan?.route.source === 'road' ? undefined : '6 9',
        }).addTo(group);
    }
    const points = markers.flatMap(({ point }) => (point ? [latLng(point)] : []));
    fit.current = () => {
      if (picking) return;
      if (points.length > 1)
        instance.fitBounds(L.latLngBounds(points), {
          paddingTopLeft: desktop ? [440, 110] : [32, 140],
          paddingBottomRight: desktop
            ? [32, 32]
            : [32, Math.max(24, Math.min(sheetHeight + 40, instance.getSize().y - 220))],
          maxZoom: 15,
        });
      else if (points.length) {
        instance.setView(points[0], 15);
        if (!desktop) instance.panBy([0, sheetHeight / 2 - 40], { animate: false });
      }
    };
    const key = JSON.stringify([pickup, dropoff, picking, desktop, sheetHeight]);
    if (!picking && framing.current !== key) {
      framing.current = key;
      fit.current();
    }
  }, [
    pickup,
    dropoff,
    driver,
    target,
    picking,
    desktop,
    sheetHeight,
    theme,
    journey.plan,
    approach.plan,
  ]);
  return (
    <Box
      data-ride-map
      sx={{
        position: 'absolute',
        inset: 0,
        bgcolor: '#E7EBE8',
        '& .leaflet-bottom.leaflet-right': {
          bottom: desktop ? 2 : `calc(${sheetHeight}px + 5px)`,
        },
        '& .leaflet-control-attribution': {
          background: '#ffffffbb',
          borderRadius: 1,
          fontSize: '10px',
        },
      }}
    >
      <Box
        ref={element}
        role="region"
        aria-label="Ride map"
        sx={{ position: 'absolute', inset: 0 }}
      />
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 110,
          pointerEvents: 'none',
          background: 'linear-gradient(#ffffff99, transparent)',
        }}
      />
      {picking && (
        <PlaceRounded
          sx={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -100%)',
            fontSize: 46,
            color: 'primary.main',
            filter: 'drop-shadow(0 3px 4px #0003)',
            pointerEvents: 'none',
          }}
        />
      )}
      {guidance && !picking && (
        <Stack
          direction="row"
          alignItems="center"
          spacing={1}
          sx={{
            position: 'absolute',
            zIndex: 400,
            top: 'calc(env(safe-area-inset-top) + 76px)',
            left: desktop ? 440 : 16,
            bgcolor: 'white',
            borderRadius: 4,
            pl: 2,
            pr: 1,
            minHeight: 44,
            boxShadow: '0 2px 14px #17244414',
          }}
        >
          <Typography fontWeight={700} variant="body2">
            {driver ? (pickedUp ? 'Drop-off' : 'Pickup') : 'Your route'}
            {guidance.duration_seconds != null &&
              ` · ${Math.max(1, Math.ceil(guidance.duration_seconds / 60))} min`}
          </Typography>
          {guidance.source === 'road' && (
            <Button
              size="small"
              color="inherit"
              onClick={() => setDirections(true)}
              sx={{ minWidth: 44, p: 1 }}
              aria-label="Directions"
            >
              <NavigationRounded fontSize="small" />
            </Button>
          )}
        </Stack>
      )}
      <Stack
        spacing={1}
        sx={{
          position: 'absolute',
          zIndex: 500,
          right: 16,
          bottom: desktop ? 28 : `calc(${sheetHeight}px + 24px)`,
        }}
      >
        {extraControl}
        <IconButton
          aria-label="Use my location"
          onClick={() => {
            if (picking && navigator.geolocation)
              navigator.geolocation.getCurrentPosition((position) => {
                const point = { lat: position.coords.latitude, lon: position.coords.longitude };
                map.current?.panTo(latLng(point));
                selection.current?.(point);
              });
            else {
              fit.current();
              onLocate?.();
            }
          }}
          sx={{
            bgcolor: 'white',
            color: 'text.primary',
            width: 48,
            height: 48,
            boxShadow: '0 2px 12px #17244422',
            '&:hover': { bgcolor: '#F5F6F8' },
          }}
        >
          <MyLocationRounded />
        </IconButton>
      </Stack>
      {unavailable && (
        <Alert
          severity="info"
          sx={{ position: 'absolute', top: 128, left: 16, right: 16, zIndex: 500 }}
        >
          Map unavailable. You can still search for a place.
        </Alert>
      )}
      <Dialog open={directions} onClose={() => setDirections(false)} fullWidth maxWidth="xs">
        <DialogTitle
          sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
        >
          Directions
          <IconButton aria-label="Close directions" onClick={() => setDirections(false)}>
            <CloseRounded />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            {guidance && `${(guidance.distance_meters / 1000).toFixed(1)} km`}
          </Typography>
          {target && driver && (
            <Button
              component="a"
              target="_blank"
              rel="noopener noreferrer"
              variant="contained"
              fullWidth
              sx={{ mb: 2 }}
              href={`https://www.google.com/maps/dir/?api=1&destination=${target.lat},${target.lon}&travelmode=driving&dir_action=navigate`}
            >
              Start navigation
            </Button>
          )}
          <Box component="ol" sx={{ pl: 2.5 }}>
            {guidance?.steps.map((step, index) => (
              <Box
                component="li"
                key={index}
                sx={{ py: 1, borderBottom: '1px solid', borderColor: 'divider' }}
              >
                <Typography>{step.instruction}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {Math.round(step.distance_meters)} m
                </Typography>
              </Box>
            ))}
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  );
}
