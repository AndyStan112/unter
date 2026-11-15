import { Box, Card, CardContent, Stack, Typography } from '@mui/material';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import { useDashboard } from '../../hooks/DashboardProvider';
import { PageHeading } from '../../components/common/PageHeading';
import { DataTable } from '../../components/common/DataTable';
import { EmptyState } from '../../components/common/EmptyState';
import { RunReportButton } from '../../components/common/RunReportButton';
export default function OverviewPage() {
  const { observations, reports, schedule } = useDashboard();
  const latest = reports[0];
  const open = latest?.report.proposals.filter(
    (p) => !latest.decisions?.[p.id] && Date.parse(p.params.ends_at) > Date.now(),
  ).length;
  const stats = [
    {
      label: 'City zones',
      value: observations.length || '—',
      note: 'Connected through the core API',
    },
    { label: 'Awaiting your decision', value: open ?? '—', note: 'Proposals in the latest report' },
    {
      label: 'Automation',
      value: schedule ? (schedule.enabled ? 'On' : 'Paused') : '—',
      note: schedule?.enabled ? schedule.cron : 'You choose when reports run',
    },
  ];
  return (
    <>
      <PageHeading
        eyebrow="The control room"
        title="Where demand meets supply."
        description="Zone metrics, surge and incentive reports, and your decisions. One connected workspace."
      />
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
          gap: 2,
          mb: 3,
        }}
      >
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="overline" color="text.secondary" sx={{ fontSize: 10 }}>
                {stat.label}
              </Typography>
              <Typography variant="h2" sx={{ my: 1.5 }} color="secondary">
                {stat.value}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {stat.note}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.4fr 1fr' }, gap: 3 }}>
        <Card>
          <CardContent sx={{ p: 3 }}>
            <Typography variant="h3" component="h2">
              A little data to work with
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Seeded zone observations for the development environment.
            </Typography>
            {observations.length ? (
              <DataTable
                rows={observations}
                rowKey={(r) => r.zone}
                columns={[
                  { label: 'Zone', render: (r) => r.zone },
                  { label: 'Demand', render: (r) => r.demand },
                  { label: 'Drivers', render: (r) => r.drivers },
                  { label: 'Wait', render: (r) => `${r.wait_minutes} min` },
                ]}
              />
            ) : (
              <EmptyState>No observations available yet.</EmptyState>
            )}
          </CardContent>
        </Card>
        <Card sx={{ bgcolor: 'secondary.main', color: '#fff' }}>
          <CardContent sx={{ p: 3 }}>
            <Stack spacing={2} alignItems="flex-start">
              <AutoAwesomeRounded sx={{ color: 'primary.light', fontSize: 36 }} />
              <Typography variant="overline">Surge & incentive agent</Typography>
              <Typography variant="h3" component="h2">
                A clearer picture of your city.
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.85 }}>
                {latest?.report.summary ||
                  'Run a report to see which zones need a surge or a driver bonus.'}
              </Typography>
              <RunReportButton />
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                {schedule ? `${schedule.model} · ${schedule.mode} mode` : 'Read-only analysis'} ·
                nothing changes until you approve.
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </>
  );
}
