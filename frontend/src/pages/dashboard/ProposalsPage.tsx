import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Button,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import { useDashboard } from '../../hooks/DashboardProvider';
import { PageHeading } from '../../components/common/PageHeading';
import { EmptyState } from '../../components/common/EmptyState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { StatusChip } from '../../components/common/StatusChip';
import { api } from '../../services/api';
import { amount } from '../../services/format';
import type { Proposal } from '../../types/dashboard';
export default function ProposalsPage() {
  const { proposals, observations, busy, online, execute } = useDashboard();
  const [zone, setZone] = useState(''),
    [reason, setReason] = useState(''),
    [confirm, setConfirm] = useState<Proposal | null>(null);
  const decide = (proposal: Proposal, status: string) =>
    execute(() => api(`proposals/${proposal.id}`, 'PATCH', { status }), `Proposal ${status}.`);
  return (
    <>
      <PageHeading
        eyebrow="In core"
        title="Your decisions, in one place."
        description="Proposals approved from reports appear here, alongside development test proposals."
      />
      <Stack spacing={2}>
        {proposals.length ? (
          proposals.map((proposal) => (
            <Card key={proposal.id}>
              <CardContent sx={{ p: 3 }}>
                <Stack spacing={2}>
                  <Stack direction="row" justifyContent="space-between" gap={1} flexWrap="wrap">
                    <Typography variant="h4" component="h2">
                      {proposal.zone} · {amount(proposal)}
                    </Typography>
                    <StatusChip label={proposal.status} />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    {proposal.reason}
                  </Typography>
                  {proposal.status === 'pending' && (
                    <Stack direction="row" gap={1}>
                      <Button
                        disabled={busy || !online}
                        variant="contained"
                        onClick={() => setConfirm(proposal)}
                      >
                        Approve
                      </Button>
                      <Button
                        disabled={busy || !online}
                        onClick={() => void decide(proposal, 'rejected')}
                      >
                        Reject
                      </Button>
                    </Stack>
                  )}
                </Stack>
              </CardContent>
            </Card>
          ))
        ) : (
          <EmptyState>No proposals in core yet.</EmptyState>
        )}
      </Stack>
      <Accordion variant="outlined" sx={{ mt: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreRounded />}>
          <Typography>Create a test proposal</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack
            component="form"
            spacing={2}
            onSubmit={async (event) => {
              event.preventDefault();
              if (
                await execute(
                  () => api('proposals', 'POST', { zone: zone || observations[0]?.zone, reason }),
                  'Test proposal created.',
                )
              )
                setReason('');
            }}
          >
            <TextField
              select
              label="Zone"
              value={zone || observations[0]?.zone || ''}
              required
              onChange={(e) => setZone(e.target.value)}
            >
              {observations.map((z) => (
                <MenuItem key={z.zone} value={z.zone}>
                  {z.zone}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              multiline
              minRows={3}
              required
              label="Reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              inputProps={{ maxLength: 1000 }}
            />
            <Button
              type="submit"
              variant="contained"
              disabled={busy || !online || !observations.length}
            >
              Create pending proposal
            </Button>
          </Stack>
        </AccordionDetails>
      </Accordion>
      <ConfirmDialog
        open={!!confirm}
        title="Approve proposal?"
        busy={busy}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm && (await decide(confirm, 'approved'))) setConfirm(null);
        }}
      >
        {confirm &&
          `${amount(confirm)} in ${confirm.zone}. ${confirm.type ? 'Approving creates the rule immediately.' : 'Approving records the decision.'}`}
      </ConfirmDialog>
    </>
  );
}
