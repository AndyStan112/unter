import type { ComponentType } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router';
import { usePageMetadata } from '../hooks/usePageMetadata';

// Router-managed imports expose actual navigation loading to the shared animation.
const page = (load: () => Promise<{ default: ComponentType }>) => async () => ({
  Component: (await load()).default,
});
function RootLayout() {
  usePageMetadata();
  return <Outlet />;
}
export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    HydrateFallback: () => null,
    children: [
      {
        path: '/ride',
        lazy: page(() => import('../layouts/RideLayout')),
        children: [
          { index: true, element: <Navigate to="/ride/passenger" replace /> },
          { path: 'index.html', element: <Navigate to="/ride/passenger" replace /> },
          { path: 'passenger', lazy: page(() => import('../pages/passenger/PassengerPage')) },
          { path: 'driver', lazy: page(() => import('../pages/driver/DriverPage')) },
          { path: '*', element: <Navigate to="/ride/passenger" replace /> },
        ],
      },
      {
        path: '/',
        lazy: page(() => import('../layouts/DashboardLayout')),
        children: [
          { index: true, lazy: page(() => import('../pages/dashboard/OverviewPage')) },
          { path: 'reports', lazy: page(() => import('../pages/dashboard/ReportsPage')) },
          { path: 'schedule', lazy: page(() => import('../pages/dashboard/SchedulePage')) },
          { path: 'activity', lazy: page(() => import('../pages/dashboard/ActivityPage')) },
          { path: 'proposals', lazy: page(() => import('../pages/dashboard/ProposalsPage')) },
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);
