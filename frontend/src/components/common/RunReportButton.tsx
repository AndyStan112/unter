import { Button } from '@mui/material';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import { useNavigate } from 'react-router';
import { useDashboard } from '../../hooks/DashboardProvider';
export function RunReportButton() {
  const { busy, online, loading, runReport } = useDashboard();
  const navigate = useNavigate();
  return (
    <Button
      variant="contained"
      startIcon={<AutoAwesomeRounded />}
      disabled={busy || !online || loading}
      onClick={async () => {
        if (await runReport()) navigate('/reports');
      }}
    >
      Run report now
    </Button>
  );
}
