import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import DirectionsCarRounded from '@mui/icons-material/DirectionsCarRounded';
import PersonOutlineRounded from '@mui/icons-material/PersonOutlineRounded';
import { Link, Outlet, useLocation } from 'react-router';
import { RideProvider, useRide } from '../hooks/RideProvider';
import { useInstall } from '../hooks/useInstall';
function Content() {
  const { online, message, busy, loading, clearMessage } = useRide();
  const { available, install } = useInstall();
  const location = useLocation();
  return (
    <Box sx={{ minHeight: '100dvh' }}>
      <Stack
        component="header"
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{
          px: { xs: 2.5, md: 5 },
          py: 2,
          borderBottom: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper',
        }}
      >
        <Stack component={Link} to="/ride/passenger" sx={{ textDecoration: 'none' }}>
          <Typography
            sx={{ fontWeight: 900, fontSize: 32, letterSpacing: '-.07em', lineHeight: 1 }}
            color="primary"
          >
            unter<span style={{ color: 'var(--mui-palette-secondary-main, #163EAB)' }}>.</span>
          </Typography>
          <Typography variant="overline" sx={{ fontSize: 9 }}>
            Ride & drive
          </Typography>
        </Stack>
        <Stack direction="row" gap={1} alignItems="center">
          <Chip
            size="small"
            label={online ? 'Connected' : 'Offline'}
            color={online ? 'secondary' : 'default'}
            variant="outlined"
          />
          {available && (
            <Button
              startIcon={<DownloadRounded />}
              variant="outlined"
              onClick={() => void install()}
            >
              Install
            </Button>
          )}
        </Stack>
      </Stack>
      {(busy || loading) && <LinearProgress />}
      <Box component="main" sx={{ px: { xs: 2, sm: 3, lg: 6 }, py: { xs: 3, md: 5 } }}>
        <Stack spacing={1} sx={{ mb: 3 }}>
          <Typography variant="overline" color="primary">
            Timișoara · On your way
          </Typography>
          <Typography component="h1" variant="h1">
            Your city.{' '}
            <Box component="span" color="secondary.main">
              Your next move.
            </Box>
          </Typography>
          <Typography color="text.secondary">Book a ride or get behind the wheel.</Typography>
        </Stack>
        <Tabs
          value={location.pathname.startsWith('/ride/driver') ? '/ride/driver' : '/ride/passenger'}
          sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab
            component={Link}
            to="/ride/passenger"
            value="/ride/passenger"
            label="Passenger"
            icon={<PersonOutlineRounded />}
            iconPosition="start"
            disabled={busy}
          />
          <Tab
            component={Link}
            to="/ride/driver"
            value="/ride/driver"
            label="Driver"
            icon={<DirectionsCarRounded />}
            iconPosition="start"
            disabled={busy}
          />
        </Tabs>
        {!online && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            You’re offline. Showing last known status. Reconnect to book or change a ride.
          </Alert>
        )}
        {message && (
          <Alert severity="info" sx={{ mb: 2 }} onClose={clearMessage}>
            {message}
          </Alert>
        )}
        <Outlet />
        <Typography
          component="footer"
          variant="caption"
          color="text.secondary"
          sx={{ mt: 4, display: 'block' }}
        >
          Take Unter with you. Install from your browser menu; on iPhone use Share → Add to Home
          Screen.
        </Typography>
      </Box>
    </Box>
  );
}
export default function RideLayout() {
  return (
    <RideProvider>
      <Content />
    </RideProvider>
  );
}
