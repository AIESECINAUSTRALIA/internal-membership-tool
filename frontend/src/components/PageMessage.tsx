import { Stack, Typography } from '@mui/material'

/** A plain page-level message: used for "not available" and "not found". */
export function PageMessage({ title, children }: { title: string; children: string }) {
  return (
    <Stack spacing={1} sx={{ maxWidth: '60ch' }}>
      <Typography variant="h1" component="h1">
        {title}
      </Typography>
      <Typography>{children}</Typography>
    </Stack>
  )
}
