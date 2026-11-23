import { Box, Chip, Divider, Stack, Typography } from '@mui/material';
import type { DriverEarnings } from '../../types/ride';
export const money = (value: number | string) => `${Number(value).toFixed(2)} RON`;
export function EarningsCard({ earnings }: { earnings: DriverEarnings | null }) {
  if (!earnings)
    return <Typography color="text.secondary">Your earnings will appear here.</Typography>;
  return (
    <Stack spacing={2.5}>
      <Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography color="text.secondary">Balance</Typography>
          <Chip label="Demo" size="small" variant="outlined" />
        </Stack>
        <Typography sx={{ fontSize: 40, fontWeight: 750, letterSpacing: '-.05em', mt: 0.5 }}>
          {money(earnings.balance)}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {earnings.completed_trips}{' '}
          {earnings.completed_trips === 1 ? 'completed ride' : 'completed rides'}
        </Typography>
      </Box>
      <Stack direction="row" spacing={2} sx={{ bgcolor: '#F4F5F7', borderRadius: '16px', p: 2 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Today
          </Typography>
          <Typography fontWeight={700}>{money(earnings.today)}</Typography>
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Bonuses
          </Typography>
          <Typography fontWeight={700}>{money(earnings.bonuses)}</Typography>
        </Box>
      </Stack>
      <Stack direction="row" justifyContent="space-between">
        <Typography color="text.secondary">Trip fares</Typography>
        <Typography>{money(earnings.fares)}</Typography>
      </Stack>
      {!!earnings.entries.length && (
        <>
          <Divider />
          <Typography fontWeight={700}>Recent earnings</Typography>
          {earnings.entries.map((entry) => (
            <Stack key={entry.trip_id} spacing={0.5}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="body2">
                  {new Date(entry.settled_at).toLocaleDateString(undefined, {
                    day: 'numeric',
                    month: 'short',
                  })}
                </Typography>
                <Typography fontWeight={700}>{money(entry.total)}</Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {money(entry.fare)} fare
                {Number(entry.bonus) > 0 && ` + ${money(entry.bonus)} bonus`}
              </Typography>
            </Stack>
          ))}
        </>
      )}
    </Stack>
  );
}
