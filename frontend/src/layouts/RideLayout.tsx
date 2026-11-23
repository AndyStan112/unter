import { useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Snackbar,
  Stack,
  ThemeProvider,
  Typography,
  createTheme,
} from '@mui/material';
import MenuRounded from '@mui/icons-material/MenuRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import DirectionsCarRounded from '@mui/icons-material/DirectionsCarRounded';
import PersonOutlineRounded from '@mui/icons-material/PersonOutlineRounded';
import HistoryRounded from '@mui/icons-material/HistoryRounded';
import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import NotificationsNoneRounded from '@mui/icons-material/NotificationsNoneRounded';
import DownloadRounded from '@mui/icons-material/DownloadRounded';
import { Outlet, useLocation, useNavigate } from 'react-router';
import theme from '../theme/theme';
import { useLoadingSignal } from '../hooks/LoadingProvider';
import { RideProvider, useRide } from '../hooks/RideProvider';
import { useInstall } from '../hooks/useInstall';
import { RideChrome, type RidePanel } from '../components/ride/RideChrome';
import { EarningsCard, money } from '../components/ride/EarningsCard';
import { TripHistory } from '../components/ride/TripHistory';
import { NotificationSettings } from '../components/ride/NotificationSettings';
const rideTheme = createTheme(theme, {
  palette: {
    primary: { main: '#182529', contrastText: '#fff' },
    text: { primary: '#182529', secondary: '#697377' },
  },
  typography: {
    h3: { fontSize: '1.4rem', fontWeight: 750, letterSpacing: '-.035em' },
    button: { fontSize: '1rem', fontWeight: 700 },
  },
  components: {
    MuiButton: { styleOverrides: { root: { borderRadius: 14, minHeight: 50 } } },
    MuiIconButton: { styleOverrides: { root: { minWidth: 44, minHeight: 44 } } },
  },
});
function Content() {
  const { session, online, message, busy, loading, history, zones, earnings, clearMessage } =
    useRide();
  const { available, install } = useInstall();
  const location = useLocation(),
    navigate = useNavigate();
  const [panel, setPanel] = useState<RidePanel>(null),
    [sheetHeight, setSheetHeight] = useState(0);
  const role = location.pathname.startsWith('/ride/driver') ? 'driver' : 'passenger';
  const profile = session.profiles[role];
  useLoadingSignal(loading);
  const close = () => setPanel(null);
  return (
    <RideChrome.Provider value={{ sheetHeight, setSheetHeight, openPanel: setPanel }}>
      <Box
        component="main"
        sx={{
          position: 'fixed',
          inset: 0,
          height: '100dvh',
          overflow: 'hidden',
          bgcolor: '#E7EBE8',
        }}
      >
        <Outlet />
        <Stack
          component="header"
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{
            position: 'absolute',
            zIndex: 700,
            top: 'calc(env(safe-area-inset-top) + 16px)',
            left: 16,
            right: 16,
            pointerEvents: 'none',
          }}
        >
          <IconButton
            aria-label="Open menu"
            onClick={() => setPanel('menu')}
            sx={{
              bgcolor: 'white',
              color: 'text.primary',
              width: 48,
              height: 48,
              boxShadow: '0 2px 16px #17244418',
              pointerEvents: 'auto',
              '&:hover': { bgcolor: 'white' },
            }}
          >
            <MenuRounded />
          </IconButton>
          <Typography
            component="span"
            sx={{
              fontWeight: 900,
              fontSize: 27,
              letterSpacing: '-.08em',
              bgcolor: 'white',
              px: 2,
              py: 0.5,
              borderRadius: 6,
              boxShadow: '0 2px 16px #17244410',
            }}
          >
            unter
            <Box component="span" sx={{ color: '#C6007E' }}>
              .
            </Box>
          </Typography>
          <Button
            aria-label={role === 'driver' ? 'Earnings' : 'Your rides'}
            onClick={() => setPanel(role === 'driver' ? 'earnings' : 'history')}
            sx={{
              bgcolor: 'white',
              color: 'text.primary',
              borderRadius: 6,
              minWidth: 48,
              minHeight: 48,
              px: role === 'driver' && earnings ? 1.5 : 1,
              boxShadow: '0 2px 16px #17244418',
              pointerEvents: 'auto',
              '&:hover': { bgcolor: 'white' },
            }}
          >
            {role === 'driver' && earnings ? (
              <Typography fontWeight={700} fontSize={14}>
                {money(earnings.today)}
              </Typography>
            ) : role === 'driver' ? (
              <AccountBalanceWalletOutlined />
            ) : (
              <HistoryRounded />
            )}
          </Button>
        </Stack>
        {(busy || loading) && (
          <LinearProgress
            sx={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 800, height: 3 }}
          />
        )}
        {!online && (
          <Alert
            severity="warning"
            sx={{ position: 'absolute', top: 76, left: 16, right: 16, zIndex: 800 }}
          >
            You’re offline. Reconnect to continue.
          </Alert>
        )}
        <Snackbar
          open={!!message}
          autoHideDuration={6000}
          onClose={clearMessage}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          sx={{ top: '80px !important' }}
        >
          <Alert severity="info" onClose={clearMessage} sx={{ boxShadow: 2 }}>
            {message}
          </Alert>
        </Snackbar>
      </Box>
      <Drawer
        open={panel === 'menu'}
        onClose={close}
        slotProps={{
          paper: {
            sx: { width: 'min(320px, 88vw)', px: 2, pt: 'max(20px, env(safe-area-inset-top))' },
          },
        }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
          <Avatar sx={{ width: 52, height: 52, bgcolor: '#EDF0F3', color: 'text.primary' }}>
            {profile?.name.charAt(0) || 'U'}
          </Avatar>
          <IconButton aria-label="Close menu" onClick={close}>
            <CloseRounded />
          </IconButton>
        </Stack>
        <Typography variant="h3" sx={{ px: 1, mb: 3 }}>
          {profile?.name || 'Welcome to Unter'}
        </Typography>
        <List>
          {[
            ['Ride', <PersonOutlineRounded />, '/ride/passenger'],
            ['Drive', <DirectionsCarRounded />, '/ride/driver'],
          ].map(([label, icon, path]) => (
            <ListItemButton
              key={String(label)}
              selected={location.pathname === path}
              onClick={() => {
                close();
                navigate(String(path));
              }}
              sx={{ borderRadius: 3 }}
            >
              <ListItemIcon>{icon}</ListItemIcon>
              <ListItemText primary={label} />
            </ListItemButton>
          ))}
          <Divider sx={{ my: 2 }} />
          <ListItemButton onClick={() => setPanel('history')}>
            <ListItemIcon>
              <HistoryRounded />
            </ListItemIcon>
            <ListItemText primary="Your rides" />
          </ListItemButton>
          {role === 'driver' && (
            <ListItemButton onClick={() => setPanel('earnings')}>
              <ListItemIcon>
                <AccountBalanceWalletOutlined />
              </ListItemIcon>
              <ListItemText primary="Earnings" />
            </ListItemButton>
          )}
          <ListItemButton onClick={() => setPanel('settings')}>
            <ListItemIcon>
              <NotificationsNoneRounded />
            </ListItemIcon>
            <ListItemText primary="Notifications" />
          </ListItemButton>
          {available && (
            <ListItemButton
              onClick={() => {
                close();
                void install();
              }}
            >
              <ListItemIcon>
                <DownloadRounded />
              </ListItemIcon>
              <ListItemText primary="Install Unter" />
            </ListItemButton>
          )}
        </List>
      </Drawer>
      <Drawer
        anchor="bottom"
        open={!!panel && panel !== 'menu'}
        onClose={close}
        slotProps={{
          paper: {
            sx: {
              borderRadius: '26px 26px 0 0',
              maxHeight: '88dvh',
              minHeight: '35dvh',
              maxWidth: { md: 440 },
              left: { md: 20 },
              bottom: { md: 20 },
              borderBottomLeftRadius: { md: 26 },
              borderBottomRightRadius: { md: 26 },
            },
          },
        }}
      >
        <Box
          sx={{ px: 2.5, pt: 2, pb: 'max(24px, env(safe-area-inset-bottom))', overflowY: 'auto' }}
        >
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            sx={{ mb: 2.5 }}
          >
            <Typography variant="h3" component="h2">
              {panel === 'earnings'
                ? 'Earnings'
                : panel === 'settings'
                  ? 'Notifications'
                  : 'Your rides'}
            </Typography>
            <IconButton aria-label="Close panel" onClick={close}>
              <CloseRounded />
            </IconButton>
          </Stack>
          {panel === 'earnings' && <EarningsCard earnings={earnings} />}
          {panel === 'history' && <TripHistory trips={history[role] || []} zones={zones} />}
          {panel === 'settings' &&
            (profile ? (
              <NotificationSettings role={role} />
            ) : (
              <Typography color="text.secondary">Add your name to enable ride updates.</Typography>
            ))}
        </Box>
      </Drawer>
    </RideChrome.Provider>
  );
}
export default function RideLayout() {
  return (
    <ThemeProvider theme={rideTheme}>
      <RideProvider>
        <Content />
      </RideProvider>
    </ThemeProvider>
  );
}
