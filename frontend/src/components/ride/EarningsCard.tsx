import { Alert, Card, CardContent, Divider, Stack, Typography } from '@mui/material';
import type { DriverEarnings } from '../../types/ride';
export const money = (value: number | string) => `${Number(value).toFixed(2)} RON`;
export function EarningsCard({ earnings }: { earnings: DriverEarnings | null }) {
  if (!earnings) return null;
  return (
    <Card>
      <CardContent sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="overline" color="primary">
            Your earnings · simulated
          </Typography>
          <Typography variant="h2" component="h2">
            {money(earnings.balance)}
          </Typography>
          <Typography color="text.secondary">
            Mock balance · {earnings.completed_trips} completed rides
          </Typography>
          <Stack direction="row" justifyContent="space-between">
            <Typography>Today · Bucharest time</Typography>
            <Typography>{money(earnings.today)}</Typography>
          </Stack>
          <Stack direction="row" justifyContent="space-between">
            <Typography>Trip fares</Typography>
            <Typography>{money(earnings.fares)}</Typography>
          </Stack>
          <Stack direction="row" justifyContent="space-between">
            <Typography>Driver bonuses</Typography>
            <Typography>{money(earnings.bonuses)}</Typography>
          </Stack>
          <Alert severity="info">Demo money. No real charges, transfers or withdrawals.</Alert>
          {!!earnings.entries.length && (
            <>
              <Divider />
              <Typography variant="h6">Recent earnings</Typography>
              {earnings.entries.map((entry) => (
                <Stack key={entry.trip_id} spacing={0.5}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>{new Date(entry.settled_at).toLocaleString()}</Typography>
                    <Typography fontWeight={700}>{money(entry.total)}</Typography>
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    Fare {money(entry.fare)} + bonus {money(entry.bonus)} · mock settled
                  </Typography>
                </Stack>
              ))}
            </>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
