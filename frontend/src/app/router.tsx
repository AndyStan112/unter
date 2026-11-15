import { lazy, Suspense } from 'react';
import { Box, CircularProgress } from '@mui/material';
import { createBrowserRouter, Navigate, Outlet } from 'react-router';
import { usePageMetadata } from '../hooks/usePageMetadata';
const DashboardLayout = lazy(() => import('../layouts/DashboardLayout'));
const RideLayout = lazy(() => import('../layouts/RideLayout'));
const OverviewPage = lazy(() => import('../pages/dashboard/OverviewPage'));
const ReportsPage = lazy(() => import('../pages/dashboard/ReportsPage'));
const SchedulePage = lazy(() => import('../pages/dashboard/SchedulePage'));
const ActivityPage = lazy(() => import('../pages/dashboard/ActivityPage'));
const ProposalsPage = lazy(() => import('../pages/dashboard/ProposalsPage'));
const PassengerPage = lazy(() => import('../pages/passenger/PassengerPage'));
const DriverPage = lazy(() => import('../pages/driver/DriverPage'));
function LoadingBoundary() {
  usePageMetadata();
  return (
    <Suspense
      fallback={
        <Box sx={{ p: 5, textAlign: 'center' }}>
          <CircularProgress aria-label="Loading page" />
        </Box>
      }
    >
      <Outlet />
    </Suspense>
  );
}
export const router = createBrowserRouter([
  {
    element: <LoadingBoundary />,
    children: [
      {
        path: '/ride',
        element: <RideLayout />,
        children: [
          { index: true, element: <Navigate to="/ride/passenger" replace /> },
          { path: 'index.html', element: <Navigate to="/ride/passenger" replace /> },
          { path: 'passenger', element: <PassengerPage /> },
          { path: 'driver', element: <DriverPage /> },
          { path: '*', element: <Navigate to="/ride/passenger" replace /> },
        ],
      },
      {
        path: '/',
        element: <DashboardLayout />,
        children: [
          { index: true, element: <OverviewPage /> },
          { path: 'reports', element: <ReportsPage /> },
          { path: 'schedule', element: <SchedulePage /> },
          { path: 'activity', element: <ActivityPage /> },
          { path: 'proposals', element: <ProposalsPage /> },
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);
