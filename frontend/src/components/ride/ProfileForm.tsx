import { useState } from 'react';
import { Button, Card, CardContent, Stack, TextField, Typography } from '@mui/material';
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded';
import { useRide } from '../../hooks/RideProvider';
import type { Role } from '../../types/ride';
export function ProfileForm({ role }: { role: Role }) {
  const { busy, online, createProfile } = useRide();
  const [name, setName] = useState('');
  return (
    <Card>
      <CardContent sx={{ p: { xs: 3, md: 4 } }}>
        <Stack
          component="form"
          spacing={3}
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) void createProfile(role, name);
          }}
        >
          <Stack spacing={1}>
            <Typography variant="h3" component="h2">
              Let’s get you moving
            </Typography>
            <Typography color="text.secondary">
              Create your {role} profile to get started.
            </Typography>
          </Stack>
          <TextField
            label="Your name"
            autoComplete="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            inputProps={{ maxLength: 100 }}
          />
          <Button
            type="submit"
            variant="contained"
            endIcon={<ArrowForwardRounded />}
            disabled={busy || !online || !name.trim()}
          >
            Continue as {role}
          </Button>
          <Typography variant="caption" color="text.secondary">
            Your profile is remembered on this browser. This development app uses the server’s
            shared login.
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}
