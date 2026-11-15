import { Chip } from '@mui/material';
export function StatusChip({ label }: { label: string }) {
  const color = /fail|reject|cancel|interrupt/i.test(label)
    ? 'error'
    : /complete|sent|approv|applied|available/i.test(label)
      ? 'success'
      : 'secondary';
  return <Chip size="small" label={label.replaceAll('_', ' ')} color={color} variant="outlined" />;
}
