import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Drawer,
  IconButton,
  InputAdornment,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseRounded from '@mui/icons-material/CloseRounded';
import SearchRounded from '@mui/icons-material/SearchRounded';
import PlaceOutlined from '@mui/icons-material/PlaceOutlined';
import MyLocationRounded from '@mui/icons-material/MyLocationRounded';
import MapOutlined from '@mui/icons-material/MapOutlined';
import { api, errorMessage } from '../../services/api';
import type { Point, Zone } from '../../types/ride';
export function LocationPicker({
  open,
  label,
  zones,
  onClose,
  onSelect,
  onMap,
  onLocate,
}: {
  open: boolean;
  label: string;
  zones: Zone[];
  onClose: () => void;
  onSelect: (point: Point) => void;
  onMap: () => void;
  onLocate?: () => void;
}) {
  const [query, setQuery] = useState(''),
    [results, setResults] = useState<Point[] | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const request = useRef(0);
  useEffect(() => {
    request.current++;
    setQuery('');
    setResults(null);
    setError('');
    setBusy(false);
  }, [open, label]);
  async function search() {
    if (query.trim().length < 3 || busy) return;
    const id = ++request.current;
    setBusy(true);
    setError('');
    try {
      const found = await api<Point[]>(`places?q=${encodeURIComponent(query.trim())}`);
      if (id === request.current) {
        setResults(found);
        if (!found.length) setError('No places found. Try another address.');
      }
    } catch (error) {
      if (id === request.current) setError(errorMessage(error));
    } finally {
      if (id === request.current) setBusy(false);
    }
  }
  return (
    <Drawer
      anchor="bottom"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            borderRadius: '26px 26px 0 0',
            height: 'min(85dvh, 700px)',
            maxWidth: { md: 440 },
            left: { md: 20 },
            bottom: { md: 20 },
            borderBottomLeftRadius: { md: 26 },
            borderBottomRightRadius: { md: 26 },
          },
        },
      }}
    >
      <Stack
        sx={{ px: 2.5, pt: 2, pb: 'max(20px, env(safe-area-inset-bottom))', height: '100%' }}
        spacing={2}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="h3" component="h2">
            {label}
          </Typography>
          <IconButton aria-label="Close address search" onClick={onClose}>
            <CloseRounded />
          </IconButton>
        </Stack>
        <Box
          component="form"
          onSubmit={(event) => {
            event.preventDefault();
            void search();
          }}
        >
          <TextField
            autoFocus
            fullWidth
            label={`${label} address`}
            placeholder="Search a place or address"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setResults(null);
              setError('');
            }}
            inputProps={{ maxLength: 200 }}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchRounded />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      type="submit"
                      aria-label="Search addresses"
                      disabled={busy || query.trim().length < 3}
                    >
                      <SearchRounded />
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
        </Box>
        {error && <Alert severity="info">{error}</Alert>}
        {busy && <Typography color="text.secondary">Searching…</Typography>}
        <Box sx={{ overflowY: 'auto', flex: 1 }}>
          <List disablePadding>
            {onLocate && (
              <ListItemButton onClick={onLocate} sx={{ minHeight: 56 }}>
                <ListItemIcon>
                  <MyLocationRounded color="primary" />
                </ListItemIcon>
                <ListItemText primary="Use my location" />
              </ListItemButton>
            )}
            <ListItemButton onClick={onMap} sx={{ minHeight: 56 }}>
              <ListItemIcon>
                <MapOutlined />
              </ListItemIcon>
              <ListItemText primary="Choose on map" />
            </ListItemButton>
            {(results || zones.map((zone) => ({ ...zone, label: zone.name }))).map(
              (point, index) => (
                <ListItemButton
                  key={index}
                  sx={{ minHeight: 60, borderBottom: '1px solid', borderColor: 'divider' }}
                  onClick={() => onSelect(point)}
                >
                  <ListItemIcon>
                    <PlaceOutlined />
                  </ListItemIcon>
                  <ListItemText
                    primary={point.label}
                    primaryTypographyProps={{ fontWeight: 600 }}
                  />
                </ListItemButton>
              ),
            )}
          </List>
        </Box>
        <Button onClick={onClose} color="inherit">
          Back to map
        </Button>
      </Stack>
    </Drawer>
  );
}
