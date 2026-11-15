import { Stack, Typography } from '@mui/material';
export function PageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <Stack spacing={1} sx={{ mb: 3 }}>
      <Typography variant="overline" color="primary">
        {eyebrow}
      </Typography>
      <Typography variant="h2" component="h1">
        {title}
      </Typography>
      <Typography color="text.secondary" sx={{ maxWidth: 720 }}>
        {description}
      </Typography>
    </Stack>
  );
}
