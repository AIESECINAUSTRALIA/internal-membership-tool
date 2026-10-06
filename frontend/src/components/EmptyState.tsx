import { Box, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'

/**
 * "No data exists" is the fixed empty-state wording used everywhere in the app (spec
 * §2A) — shown for a chart placeholder until the KPI catalog exists (spec §4.3 TODO),
 * and reused for any later chart with nothing to plot.
 */
export function EmptyChartState() {
  return (
    <Typography variant="h3" component="p" sx={{ mt: 4, mb: 2 }}>
      No data exists
    </Typography>
  )
}

/**
 * A table shown with a single "No data exists" placeholder row (spec §2A) — the shape
 * Data's summary and Tracking's KPI tables share while the KPI catalog is still a spec
 * TODO (§4.3). Pass the header columns; the placeholder row spans all of them.
 */
export function EmptyDataTable({ label, columns }: { label: string; columns: string[] }) {
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Table size="small" aria-label={label}>
        <TableHead>
          <TableRow>
            {columns.map((column) => (
              <TableCell key={column}>{column}</TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow>
            <TableCell colSpan={columns.length}>
              <Typography sx={{ py: 1 }}>No data exists</Typography>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Box>
  )
}
