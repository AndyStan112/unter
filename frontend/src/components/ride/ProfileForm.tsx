import { useState } from 'react';
import { Button, Stack, TextField, Typography } from '@mui/material';
import { useRide } from '../../hooks/RideProvider';
import type { Role } from '../../types/ride';
export function ProfileForm({ role }: { role: Role }) {
  const { busy, online, createProfile } = useRide();
  const [name, setName] = useState('');
  return (
    <Stack
      component="form"
      spacing={2.5}
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) void createProfile(role, name);
      }}
    >
      <Typography variant="h3" component="h1">
        What’s your name?
      </Typography>
      <TextField
        label="Your name"
        autoComplete="name"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
        inputProps={{ maxLength: 80 }}
        fullWidth
      />
      <Button
        type="submit"
        fullWidth
        variant="contained"
        disabled={busy || !online || !name.trim()}
      >
        Continue
      </Button>
    </Stack>
  );
}
