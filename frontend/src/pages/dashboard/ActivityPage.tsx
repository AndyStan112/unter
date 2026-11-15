import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Stack,
  Typography,
} from '@mui/material';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import { useDashboard } from '../../hooks/DashboardProvider';
import { PageHeading } from '../../components/common/PageHeading';
import { EmptyState } from '../../components/common/EmptyState';
import { date } from '../../services/format';
export default function ActivityPage() {
  const { activity } = useDashboard();
  return (
    <>
      <PageHeading
        eyebrow="The event pipeline"
        title="A record of what happened."
        description="Events delivered from the core and agent through RabbitMQ to the activity worker."
      />
      {!activity.length && <EmptyState>Waiting for the first event.</EmptyState>}
      {activity.map((event) => (
        <Accordion key={event.id} variant="outlined" disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreRounded />}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              justifyContent="space-between"
              sx={{ width: '100%', pr: 2 }}
              gap={1}
            >
              <Typography fontWeight={600}>{event.kind}</Typography>
              <Typography variant="caption" color="text.secondary">
                {date(event.created_at)}
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Box component="pre" sx={{ m: 0, fontSize: 12 }}>
              {JSON.stringify(event.payload, null, 2)}
            </Box>
          </AccordionDetails>
        </Accordion>
      ))}
    </>
  );
}
