import { useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material';
import DashboardRounded from '@mui/icons-material/DashboardRounded';
import DescriptionRounded from '@mui/icons-material/DescriptionRounded';
import ScheduleRounded from '@mui/icons-material/ScheduleRounded';
import BoltRounded from '@mui/icons-material/BoltRounded';
import FactCheckRounded from '@mui/icons-material/FactCheckRounded';
import MenuRounded from '@mui/icons-material/MenuRounded';
import RefreshRounded from '@mui/icons-material/RefreshRounded';
import ArrowOutwardRounded from '@mui/icons-material/ArrowOutwardRounded';
import { Link, NavLink, Outlet, useLocation } from 'react-router';
import { DashboardProvider, useDashboard } from '../hooks/DashboardProvider';
const navigation = [
  { path: '/', title: 'Overview', icon: DashboardRounded },
  { path: '/reports', title: 'Reports', icon: DescriptionRounded },
  { path: '/schedule', title: 'Schedule & runs', icon: ScheduleRounded },
  { path: '/activity', title: 'Event activity', icon: BoltRounded },
  { path: '/proposals', title: 'Proposals', icon: FactCheckRounded },
];
function Content() {
  const [open, setOpen] = useState(false);
  const { loading, busy, online, message, clearMessage, refresh } = useDashboard();
  const location = useLocation();
  const sidebar = (
    <Stack sx={{ p: 3, height: '100%', color: 'white', bgcolor: 'secondary.dark' }}>
      <Typography
        component={Link}
        to="/"
        sx={{
          textDecoration: 'none',
          fontWeight: 900,
          fontSize: 38,
          letterSpacing: '-.07em',
          mb: 4,
        }}
      >
        unter
        <Box component="span" sx={{ color: 'primary.light' }}>
          .
        </Box>
      </Typography>
      <Typography variant="overline" sx={{ opacity: 0.65, fontSize: 10 }}>
        Control room
      </Typography>
      <Typography variant="body2" sx={{ mb: 3, opacity: 0.8 }}>
        Your city, in perspective.
      </Typography>
      <List sx={{ mx: -1 }}>
        {navigation.map(({ path, title, icon: Icon }) => (
          <ListItemButton
            key={path}
            component={NavLink}
            end={path === '/'}
            to={path}
            onClick={() => setOpen(false)}
            sx={{
              borderRadius: 2,
              mb: 0.75,
              color: '#DCE5FF',
              '&.active': {
                bgcolor: 'rgba(255,255,255,.13)',
                color: '#fff',
                boxShadow: 'inset 3px 0 #F49BD5',
              },
            }}
          >
            <ListItemIcon sx={{ color: 'inherit', minWidth: 36 }}>
              <Icon fontSize="small" />
            </ListItemIcon>
            <ListItemText
              primary={title}
              primaryTypographyProps={{ fontSize: 14, fontWeight: 600 }}
            />
          </ListItemButton>
        ))}
      </List>
      <Box sx={{ mt: 'auto', pt: 4 }}>
        <Button
          component="a"
          href="/ride/"
          fullWidth
          endIcon={<ArrowOutwardRounded />}
          sx={{ color: '#fff', border: '1px solid rgba(255,255,255,.3)' }}
        >
          Open ride app
        </Button>
        <Typography variant="caption" sx={{ display: 'block', mt: 2, opacity: 0.6 }}>
          Development workspace · v0.3
        </Typography>
      </Box>
    </Stack>
  );
  return (
    <Box sx={{ display: 'flex', minHeight: '100dvh' }}>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          width: 248,
          flexShrink: 0,
          '& .MuiDrawer-paper': { width: 248, border: 0 },
        }}
      >
        {sidebar}
      </Drawer>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        sx={{ '& .MuiDrawer-paper': { width: 270 } }}
      >
        {sidebar}
      </Drawer>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <AppBar
          component="header"
          position="static"
          color="transparent"
          elevation={0}
          sx={{ bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}
        >
          <Toolbar sx={{ gap: 1.5 }}>
            <IconButton
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
              sx={{ display: { md: 'none' } }}
            >
              <MenuRounded />
            </IconButton>
            <Typography variant="body2" sx={{ flex: 1 }}>
              {navigation.find((n) => n.path === location.pathname)?.title || 'Workspace'}
            </Typography>
            <Chip
              size="small"
              label={online ? 'Connected' : 'Offline'}
              color={online ? 'secondary' : 'default'}
              variant="outlined"
            />
            <Button
              disabled={busy || loading || !online}
              onClick={() => void refresh()}
              startIcon={<RefreshRounded />}
            >
              Refresh
            </Button>
          </Toolbar>
        </AppBar>
        {(loading || busy) && <LinearProgress />}
        <Box component="main" sx={{ p: { xs: 2.5, md: 4, xl: 6 } }}>
          {!online && (
            <Alert severity="warning" sx={{ mb: 3 }}>
              You’re offline. Reconnect for live data and actions.
            </Alert>
          )}
          {message && (
            <Alert severity="info" onClose={clearMessage} sx={{ mb: 3 }}>
              {message}
            </Alert>
          )}
          <Outlet />
          <Typography
            component="footer"
            variant="caption"
            color="text.secondary"
            sx={{ mt: 5, display: 'block' }}
          >
            Unter / control room · Rules decide. People approve.
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
export default function DashboardLayout() {
  return (
    <DashboardProvider>
      <Content />
    </DashboardProvider>
  );
}
