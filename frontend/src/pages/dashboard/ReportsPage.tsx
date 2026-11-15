import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import { useDashboard } from '../../hooks/DashboardProvider';
import { PageHeading } from '../../components/common/PageHeading';
import { EmptyState } from '../../components/common/EmptyState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { DataTable, type Column } from '../../components/common/DataTable';
import { StatusChip } from '../../components/common/StatusChip';
import { amount, date, percent } from '../../services/format';
import { api } from '../../services/api';
import type { Proposal, Report, ZoneMetrics } from '../../types/dashboard';
const metricColumns: Column<ZoneMetrics>[] = [
  { label: 'Zone', render: (z) => z.zone },
  { label: 'Requests', render: (z) => z.requests },
  { label: 'Per hour', render: (z) => z.requests_per_hour },
  { label: 'Unmatched', render: (z) => percent(z.unmatched_rate) },
  { label: 'Cancelled', render: (z) => percent(z.cancel_rate) },
  {
    label: 'Worst p90 wait',
    render: (z) => (z.worst_p90_wait_s == null ? '—' : `${Math.round(z.worst_p90_wait_s)}s`),
  },
  { label: 'Net flow', render: (z) => z.net_flow },
  { label: 'Drivers now', render: (z) => z.supply_now?.available ?? '—' },
  { label: 'Demand / supply', render: (z) => z.demand_supply_ratio ?? '—' },
];
const deliveryLabels: Record<string, string> = {
  sent: 'Emailed',
  sending: 'Sending email',
  failed: 'Email failed, retrying',
  parked: 'Email failed',
  skipped: 'No recipients',
  not_configured: 'Email not configured',
};
const decisionLabels: Record<string, string> = {
  applied: 'Approved · rule active',
  created: 'Created in core · approve under Proposals',
  rejected: 'Rejected',
  applying: 'Applying…',
};
function ReportCard({ row }: { row: Report }) {
  const { busy, online, execute } = useDashboard();
  const [confirm, setConfirm] = useState<Proposal | null>(null);
  const decide = (proposal: Proposal, decision: 'approved' | 'rejected') =>
    execute(
      () => api(`reports/${row.id}/decisions`, 'POST', { proposal_id: proposal.id, decision }),
      `${proposal.zone}: proposal ${decision}.`,
    );
  const report = row.report;
  return (
    <Card>
      <CardContent sx={{ p: { xs: 2.5, md: 3 } }}>
        <Stack spacing={2.5}>
          <Stack
            direction="row"
            gap={1}
            justifyContent="space-between"
            alignItems="center"
            flexWrap="wrap"
          >
            <Typography variant="body2" fontWeight={600}>
              {date(report.window.from)} → {date(report.window.to)}
            </Typography>
            <Stack direction="row" gap={1} flexWrap="wrap">
              <Chip
                size="small"
                label={
                  report.explained_by === 'model' ? `Text by ${report.model}` : 'Template text'
                }
                variant="outlined"
              />
              <StatusChip
                label={
                  row.delivery
                    ? deliveryLabels[row.delivery.status] || row.delivery.status
                    : row.published
                      ? 'Published'
                      : 'Publishing…'
                }
              />
            </Stack>
          </Stack>
          <Typography>{report.summary}</Typography>
          <Divider />
          {!report.proposals.length && (
            <Typography color="text.secondary">No proposals in this report.</Typography>
          )}
          {report.proposals.map((proposal) => {
            const decision = row.decisions?.[proposal.id],
              expired = Date.parse(proposal.params.ends_at) <= Date.now();
            return (
              <Box
                key={proposal.id}
                sx={{ p: 2.5, border: 1, borderColor: 'divider', borderRadius: 2 }}
              >
                <Stack spacing={1.5}>
                  <Stack direction="row" justifyContent="space-between" flexWrap="wrap" gap={1}>
                    <Typography variant="h6">
                      {proposal.zone} · {amount(proposal)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {date(proposal.params.starts_at)} → {date(proposal.params.ends_at)}
                    </Typography>
                  </Stack>
                  <Typography variant="body2">{proposal.reason}</Typography>
                  {proposal.rule && (
                    <Typography variant="caption" color="text.secondary">
                      Rule: {proposal.rule}
                    </Typography>
                  )}
                  <Stack direction="row" gap={1}>
                    {decision ? (
                      <StatusChip label={decisionLabels[decision.status] || decision.status} />
                    ) : expired ? (
                      <Chip size="small" label="Expired" />
                    ) : (
                      <>
                        <Button
                          variant="contained"
                          size="small"
                          disabled={busy || !online}
                          onClick={() => setConfirm(proposal)}
                        >
                          Approve
                        </Button>
                        <Button
                          size="small"
                          disabled={busy || !online}
                          onClick={() => void decide(proposal, 'rejected')}
                        >
                          Reject
                        </Button>
                      </>
                    )}
                  </Stack>
                </Stack>
              </Box>
            );
          })}
          {!!report.skipped?.length && (
            <Typography variant="caption" color="text.secondary">
              Skipped: {report.skipped.map((s) => `${s.zone} (${s.reason})`).join('; ')}
            </Typography>
          )}
          <Accordion disableGutters elevation={0} sx={{ '&::before': { display: 'none' } }}>
            <AccordionSummary expandIcon={<ExpandMoreRounded />}>
              <Typography variant="body2">Zone metrics · created {date(row.created_at)}</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ px: 0 }}>
              <DataTable rows={report.zones} columns={metricColumns} rowKey={(z) => z.zone} />
              {row.delivery?.last_error && (
                <Typography variant="caption" color="error">
                  {row.delivery.last_error}
                </Typography>
              )}
            </AccordionDetails>
          </Accordion>
        </Stack>
      </CardContent>
      <ConfirmDialog
        open={!!confirm}
        title="Approve this proposal?"
        busy={busy}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm && (await decide(confirm, 'approved'))) setConfirm(null);
        }}
      >
        {confirm &&
          `${amount(confirm)} in ${confirm.zone}. This creates the rule in core under your login.`}
      </ConfirmDialog>
    </Card>
  );
}
export default function ReportsPage() {
  const { reports } = useDashboard();
  return (
    <>
      <PageHeading
        eyebrow="Human in the loop"
        title="Proposals, with their reasons."
        description="Review surge rates and driver bonuses. The agent proposes; you decide what takes effect."
      />
      <Stack spacing={3}>
        {reports.length ? (
          reports.map((row) => <ReportCard key={row.id} row={row} />)
        ) : (
          <EmptyState>No reports yet. Run one from Overview or set a schedule.</EmptyState>
        )}
      </Stack>
    </>
  );
}
