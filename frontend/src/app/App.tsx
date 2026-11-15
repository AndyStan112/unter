import { useSyncExternalStore } from 'react';
import { LoadingProvider } from '../hooks/LoadingProvider';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { RouterProvider } from 'react-router';
import theme from '../theme/theme';
import { router } from './router';
const navigationLoading = () =>
  !router.state.initialized || router.state.navigation.state !== 'idle';
export default function App() {
  const loading = useSyncExternalStore(router.subscribe, navigationLoading);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <LoadingProvider loading={loading}>
        <RouterProvider router={router} />
      </LoadingProvider>
    </ThemeProvider>
  );
}
