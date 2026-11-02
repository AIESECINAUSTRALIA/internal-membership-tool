import { Box, Paper, Stack, Typography } from '@mui/material'

/**
 * Auditing (spec §2A.10): a read-only view of the audit log, admins only. Not built
 * yet — there is no `audit_log` table (spec §4.5, §8.4) to read from. The route and
 * nav item exist now so the console's shape is right; the content is a placeholder in
 * the same "Not built yet" wording as `NotBuiltYetDialog`, since a whole unbuilt PAGE
 * has nothing to open a dialog from.
 */
export function AdminAuditingPage() {
  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h1" component="h1">
          Auditing
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
          Who did what, and when, across the application.
        </Typography>
      </Box>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary" sx={{ maxWidth: '65ch' }}>
          Not built yet. This will show a read-only log of every create, edit, deactivate and sign-in, with filters
          for date range, actor and action type.
        </Typography>
      </Paper>
    </Stack>
  )
}
