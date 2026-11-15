import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardContent,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import { useDashboard } from '../../hooks/DashboardProvider';
import { PageHeading } from '../../components/common/PageHeading';
import { RunReportButton } from '../../components/common/RunReportButton';
import { StatusChip } from '../../components/common/StatusChip';
import { EmptyState } from '../../components/common/EmptyState';
import { date } from '../../services/format';
import { api } from '../../services/api';
import type { Schedule } from '../../types/dashboard';
function ScheduleForm({ initial }: { initial: Schedule }) {
  const { execute, busy, online, schedule } = useDashboard();
  const [draft, setDraft] = useState(initial),
    [recipients, setRecipients] = useState(initial.recipients.join('\n'));
  const field = (key: keyof Schedule, value: string | number | boolean) =>
    setDraft((old) => ({ ...old, [key]: value }));
  return (
    <Stack
      component="form"
      spacing={2.5}
      onSubmit={(event) => {
        event.preventDefault();
        void execute(
          () =>
            api('schedule', 'PUT', {
              cron: draft.cron,
              timezone: draft.timezone,
              enabled: draft.enabled,
              window_hours: draft.window_hours,
              recipients: recipients
                .split(/[\n,;]+/)
                .map((s) => s.trim())
                .filter(Boolean),
            }),
          'Schedule saved.',
        );
      }}
    >
      <Typography variant="h3" component="h2">
        Report schedule
      </Typography>
      <TextField
        label="Cron expression"
        value={draft.cron}
        onChange={(e) => field('cron', e.target.value)}
        required
        helperText="Minute · hour · day · month · weekday"
        inputProps={{ maxLength: 80 }}
      />
      <TextField
        label="Timezone"
        value={draft.timezone}
        onChange={(e) => field('timezone', e.target.value)}
        required
        inputProps={{ maxLength: 80 }}
      />
      <TextField
        type="number"
        label="Analysis window (hours)"
        value={draft.window_hours}
        onChange={(e) => field('window_hours', Number(e.target.value))}
        required
        inputProps={{ min: 1, max: 168, step: 1 }}
      />
      <TextField
        multiline
        minRows={3}
        label="Email recipients"
        value={recipients}
        onChange={(e) => setRecipients(e.target.value)}
        inputProps={{ maxLength: 5500 }}
        helperText="One per line, at most 20. Leave empty to only store reports."
      />
      <FormControlLabel
        control={
          <Switch checked={draft.enabled} onChange={(e) => field('enabled', e.target.checked)} />
        }
        label="Enable scheduled runs"
      />
      <Typography variant="body2" color="text.secondary">
        {schedule?.enabled
          ? `Next slot: ${date(schedule.next_at)}`
          : 'Schedule paused. Manual runs remain available.'}
      </Typography>
      <Button type="submit" variant="contained" disabled={busy || !online}>
        Save schedule
      </Button>
    </Stack>
  );
}
export default function SchedulePage() {
  const { schedule, runs } = useDashboard();
  return (
    <>
      <PageHeading
        eyebrow="Automation, at your pace"
        title="Reports on your schedule."
        description="Choose when the agent analyses trip data, which period it covers, and who gets the email."
      />
      <Box
        sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 3, mb: 4 }}
      >
        <Card>
          <CardContent sx={{ p: 3 }}>
            {schedule ? (
              <ScheduleForm initial={schedule} />
            ) : (
              <EmptyState>Loading schedule…</EmptyState>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent sx={{ p: 3 }}>
            <Stack spacing={3} alignItems="flex-start">
              <Typography variant="h3" component="h2">
                A report, in four steps.
              </Typography>
              {[
                'Read zone metrics through the read-only MCP server.',
                'Use fixed rules to propose surge rates and driver bonuses.',
                'Write the reasons and a summary.',
                'Store the report and email the recipients.',
              ].map((step, i) => (
                <Typography key={step} variant="body2" color="text.secondary">
                  <Box component="strong" color="primary.main" sx={{ mr: 1 }}>
                    {String(i + 1).padStart(2, '0')}
                  </Box>
                  {step}
                </Typography>
              ))}
              <RunReportButton />
              <Typography variant="caption" color="text.secondary">
                {schedule?.max_daily_runs ?? '—'} runs per UTC day, one at a time. 30 seconds
                between runs. Nothing changes until you approve.
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      </Box>
      <Typography variant="h3" component="h2" sx={{ mb: 2 }}>
        Execution history
      </Typography>
      {!runs.length && <EmptyState>No runs yet.</EmptyState>}
      {runs.map((run) => (
        <Accordion key={run.id} variant="outlined" disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreRounded />}>
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
              <StatusChip label={run.status} />
              <Typography variant="body2">
                {run.source === 'schedule' ? 'Scheduled' : 'Manual'} · {date(run.started_at)}
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption" color="text.secondary">
              {run.model} · {run.mode} · MCP: {run.tool_calls?.join(', ') || '—'}
            </Typography>
            {(run.result || run.error) && (
              <Box component="pre" sx={{ fontSize: 12 }}>
                {run.result || run.error}
              </Box>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
    </>
  );
}
