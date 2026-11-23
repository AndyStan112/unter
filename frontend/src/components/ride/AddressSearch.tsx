import { useState } from 'react';
import {
  Alert,
  Button,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { api, errorMessage } from '../../services/api';
import type { Point } from '../../types/ride';
export function AddressSearch({
  label,
  onSelect,
  disabled,
}: {
  label: string;
  onSelect: (point: Point) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState(''),
    [results, setResults] = useState<Point[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function search() {
    setBusy(true);
    setError('');
    setResults([]);
    try {
      const found = await api<Point[]>(`places?q=${encodeURIComponent(query.trim())}`);
      setResults(found);
      if (!found.length) setError('No addresses found. Try including the city.');
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1}>
        <TextField
          fullWidth
          size="small"
          label={`${label} address`}
          value={query}
          disabled={disabled || busy}
          onChange={(e) => setQuery(e.target.value)}
          inputProps={{ maxLength: 200 }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              if (query.trim().length >= 3 && !busy && !disabled) void search();
            }
          }}
        />
        <Button
          type="button"
          onClick={() => void search()}
          disabled={disabled || busy || query.trim().length < 3}
        >
          {busy ? 'Searching…' : 'Search'}
        </Button>
      </Stack>
      {error && <Alert severity="info">{error}</Alert>}
      {!!results.length && (
        <List dense aria-label={`${label} address results`}>
          {results.map((point, i) => (
            <ListItemButton
              key={i}
              disabled={disabled}
              onClick={() => {
                onSelect(point);
                setQuery(point.label || '');
                setResults([]);
              }}
            >
              <ListItemText primary={point.label} />
            </ListItemButton>
          ))}
        </List>
      )}
      <Typography variant="caption" color="text.secondary">
        Address search: Photon / OpenStreetMap contributors
      </Typography>
    </Stack>
  );
}
