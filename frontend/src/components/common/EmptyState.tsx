import { Box, Typography } from '@mui/material';
export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ py: 5, px: 2, textAlign: 'center' }}>
      <Typography color="text.secondary">{children}</Typography>
    </Box>
  );
}
